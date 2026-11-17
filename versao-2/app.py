"""Servidor e API da Agenda Acadêmica — versão 2.3 (Python 3, sem dependências)."""

from __future__ import annotations

import csv
import errno
import hashlib
import io
import json
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


VERSION = "2.3"
ROOT = Path(__file__).resolve().parent
PRIORITIES = ("baixa", "media", "alta")
PRIORITY_LABELS = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    due_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    priority TEXT NOT NULL DEFAULT 'media' CHECK (priority IN ('baixa', 'media', 'alta')),
    due_time TEXT NOT NULL DEFAULT '',
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    answer_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL
);
"""
# Horário vazio = o prazo vale até o fim do dia.
END_OF_DAY = "23:59"
# Pendentes primeiro, depois o prazo mais próximo (data e horário) e, no mesmo prazo, a prioridade mais alta.
ORDER_BY = (
    f"ORDER BY completed ASC, due_date ASC, CASE due_time WHEN '' THEN '{END_OF_DAY}' ELSE due_time END ASC, "
    "CASE priority WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END, id DESC"
)

# Contas (versão 2.3)
SESSION_COOKIE = "agenda_sessao"
SESSION_DURATION = timedelta(days=7)
PBKDF2_ROUNDS = 600_000  # valor recomendado pela OWASP para PBKDF2-HMAC-SHA256
USERNAME_PATTERN = re.compile(r"[a-z0-9._-]{3,30}")
USERNAME_RULE = "O usuário deve ter de 3 a 30 caracteres: letras sem acento, números, ponto, hífen ou sublinhado."
MAX_ATTEMPTS = 5
BLOCK_SECONDS = 15 * 60
TOO_MANY_ATTEMPTS = "Muitas tentativas erradas para este usuário. Aguarde 15 minutos e tente novamente."


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path):
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate(connection: sqlite3.Connection) -> None:
    """Atualiza bancos de versões anteriores: a 1.0 não tinha prioridade, a 2.1 não tinha horário e a 2.2 não tinha contas."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
    if "priority" not in columns:
        connection.execute(
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'media' "
            "CHECK (priority IN ('baixa', 'media', 'alta'))"
        )
    if "due_time" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN due_time TEXT NOT NULL DEFAULT ''")
    if "user_id" not in columns:
        # Tarefas antigas ficam sem dono até a primeira conta ser criada (veja adopt_orphan_tasks).
        connection.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER REFERENCES users(id)")
    connection.execute("CREATE INDEX IF NOT EXISTS tasks_by_user ON tasks (user_id)")


def initialize(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        migrate(connection)


def seed_project_plan(db_path: Path, today: date | None = None) -> int:
    """Cria um plano inicial da PIT somente em um banco novo e vazio (fica com a primeira conta)."""
    today = today or date.today()
    plan = [
        ("Consolidar a documentação da Agenda Acadêmica", "PIT · Documentação", 0, True, "media",
         "Objetivo, requisitos RF01–RF07, regras, fluxo e arquitetura Python/SQLite reunidos em DOCUMENTACAO_PROJETO.md."),
        ("Preencher os dados técnicos no formulário PIT", "PIT · Entrega", 0, True, "media",
         "Back-end Python 3, banco SQLite, plataforma web e modo tradicional registrados em PIT_atividade_preenchida.docx. Nome, RGM e links ainda faltam."),
        ("Executar os testes locais e registrar correções", "PIT · Qualidade", 0, True, "alta",
         "Testes de integração aprovados; a correção do fechamento da conexão SQLite está descrita em LAUDO_QUALIDADE.md."),
        ("Preparar o roteiro do vídeo narrado", "PIT · Vídeo", 0, True, "baixa",
         "Roteiro de cerca de 5min40 em ROTEIROS_DE_VIDEO.md: objetivo, cadastro, filtros, edição, persistência, código e laudo."),
        ("Revisar a documentação com a PIT I", "PIT · Documentação", 2, False, "media",
         "Comparar a documentação atual com a versão da PIT I e com o material teórico da disciplina; ajustar pontos ausentes."),
        ("Realizar cinco testes com participantes", "PIT · Testes", 3, False, "alta",
         "Convidar cinco pessoas disponíveis ou confirmar uma alternativa com o professor. Registrar data e resultado depois de cada teste."),
        ("Gravar o vídeo narrado da aplicação", "PIT · Vídeo", 5, False, "alta",
         "Vídeo de no mínimo 5min. Demonstrar cadastro, edição, conclusão, filtros e persistência; conferir o link depois do envio."),
        ("Criar repositório e publicar a aplicação", "PIT · Publicação", 7, False, "alta",
         "Criar a conta GitHub, enviar código e documentação e obter um endereço público para a aplicação."),
        ("Preencher nome, RGM e links finais da PIT", "PIT · Entrega", 9, False, "media",
         "Conferir dados pessoais, endereço do repositório, link da aplicação e vídeos antes de enviar o formulário."),
        ("Gravar o vídeo das correções após feedback", "PIT · Vídeo", 10, False, "media",
         "Vídeo de até 5min com problema observado, alteração realizada e reteste. Depende das avaliações e correções pertinentes."),
    ]
    now = utc_now()
    with connect(db_path) as connection:
        if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] != 0:
            return 0
        connection.executemany(
            "INSERT INTO tasks (title, subject, due_date, notes, completed, priority, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(title, subject, (today + timedelta(days=days)).isoformat(), notes,
              int(completed), priority, now, now)
             for title, subject, days, completed, priority, notes in plan],
        )
    return len(plan)


def validate_task(data: object) -> tuple[dict | None, str | None]:
    if not isinstance(data, dict):
        return None, "Envie um objeto JSON válido."
    title = data.get("title")
    subject = data.get("subject")
    due_date = data.get("due_date")
    due_time = data.get("due_time", "")
    notes = data.get("notes", "")
    completed = data.get("completed", False)
    priority = data.get("priority", "media")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        return None, "O título deve ter entre 1 e 120 caracteres."
    if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 80:
        return None, "A disciplina deve ter entre 1 e 80 caracteres."
    if not isinstance(due_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
        return None, "Informe uma data de entrega válida."
    try:
        date.fromisoformat(due_date)
    except ValueError:
        return None, "Informe uma data de entrega válida."
    # Horário opcional, no formato 24 h (HH:MM) que o campo de horário do navegador envia.
    if not isinstance(due_time, str) or (due_time and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", due_time)):
        return None, "Informe um horário de entrega válido (HH:MM) ou deixe o campo vazio."
    if not isinstance(notes, str) or len(notes) > 500:
        return None, "As observações devem ter até 500 caracteres."
    if not isinstance(completed, bool):
        return None, "O estado da tarefa deve ser verdadeiro ou falso."
    if priority not in PRIORITIES:
        return None, "A prioridade deve ser baixa, média ou alta."
    return {
        "title": title.strip(),
        "subject": subject.strip(),
        "due_date": due_date,
        "due_time": due_time,
        "notes": notes.strip(),
        "completed": int(completed),
        "priority": priority,
    }, None


# ---------------------------------------------------------------- contas

def hash_secret(secret: str) -> str:
    """Senha (ou resposta secreta) nunca é gravada: só o resultado do PBKDF2 com um sal aleatório."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def check_secret(secret: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), bytes.fromhex(salt), int(rounds))
    except ValueError:
        return False
    return secrets.compare_digest(candidate.hex(), digest)


def normalize_answer(answer: str) -> str:
    """'  São   Paulo ' e 'sao paulo' contam como a mesma resposta."""
    without_accents = "".join(char for char in unicodedata.normalize("NFD", answer) if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())


def normalize_username(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def password_error(password: object) -> str | None:
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        return "A senha deve ter pelo menos 8 caracteres."
    return None


def validate_account(data: object) -> tuple[dict | None, str | None]:
    if not isinstance(data, dict):
        return None, "Envie um objeto JSON válido."
    name = data.get("name")
    username = normalize_username(data.get("username"))
    question = data.get("question")
    answer = data.get("answer")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        return None, "Informe o seu nome (até 80 caracteres)."
    if not USERNAME_PATTERN.fullmatch(username):
        return None, USERNAME_RULE
    error = password_error(data.get("password"))
    if error:
        return None, error
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 120:
        return None, "Escreva uma pergunta secreta (de 5 a 120 caracteres)."
    if not isinstance(answer, str) or not 2 <= len(normalize_answer(answer)) <= 80:
        return None, "Escreva a resposta da pergunta secreta (de 2 a 80 caracteres)."
    return {
        "name": " ".join(name.split()),
        "username": username,
        "password": data["password"],
        "question": question.strip(),
        "answer": answer,
    }, None


def adopt_orphan_tasks(connection: sqlite3.Connection, user_id: int) -> None:
    """Tarefas sem dono (plano inicial e bancos de versões anteriores) passam para a conta indicada."""
    connection.execute("UPDATE tasks SET user_id = ? WHERE user_id IS NULL", (user_id,))


def ensure_account(db_path: Path, username: str, password: str, name: str = "Avaliador") -> int:
    """Cria (ou atualiza a senha da) conta definida por AGENDA_USUARIO e AGENDA_SENHA na hospedagem."""
    username = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(username):
        raise SystemExit(f"AGENDA_USUARIO inválido. {USERNAME_RULE}")
    with connect(db_path) as connection:
        row = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            user_id = row["id"]
            connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_secret(password), user_id))
        else:
            # Sem pergunta secreta: a senha desta conta só muda pelo painel da hospedagem.
            user_id = connection.execute(
                "INSERT INTO users (name, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, username, hash_secret(password), utc_now()),
            ).lastrowid
        adopt_orphan_tasks(connection, user_id)
    return user_id


def token_digest(token: str) -> str:
    """O banco guarda só o hash do token da sessão; quem lê o banco não consegue entrar como outra pessoa."""
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


class AttemptLimiter:
    """Depois de MAX_ATTEMPTS erros seguidos para o mesmo usuário, bloqueia novas tentativas por BLOCK_SECONDS."""

    def __init__(self) -> None:
        self.failures: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def recent(self, key: str) -> list[float]:
        now = time.monotonic()
        return [moment for moment in self.failures.get(key, []) if now - moment < BLOCK_SECONDS]

    def blocked(self, key: str) -> bool:
        with self.lock:
            self.failures[key] = self.recent(key)
            return len(self.failures[key]) >= MAX_ATTEMPTS

    def failed(self, key: str) -> None:
        with self.lock:
            self.failures[key] = self.recent(key) + [time.monotonic()]

    def reset(self, *keys: str) -> None:
        with self.lock:
            for key in keys:
                self.failures.pop(key, None)


def public_user(row: sqlite3.Row) -> dict:
    return {"name": row["name"], "username": row["username"]}


# ---------------------------------------------------------------- tarefas e planilha

def serialize(row: sqlite3.Row) -> dict:
    item = dict(row)
    item.pop("user_id", None)
    item["completed"] = bool(item["completed"])
    return item


def csv_safe(value: str) -> str:
    """Evita que o Excel interprete textos começados por =, +, - ou @ como fórmulas."""
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def tasks_to_csv(rows: list[sqlite3.Row]) -> bytes:
    """Gera a planilha com ';' como separador e BOM UTF-8, o formato que o Excel em português abre direto."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(["ID", "Título", "Disciplina", "Prioridade", "Data de entrega", "Horário", "Situação", "Observações"])
    for row in rows:
        writer.writerow([
            row["id"],
            csv_safe(row["title"]),
            csv_safe(row["subject"]),
            PRIORITY_LABELS[row["priority"]],
            date.fromisoformat(row["due_date"]).strftime("%d/%m/%Y"),
            row["due_time"],
            "Concluída" if row["completed"] else "Pendente",
            csv_safe(row["notes"]),
        ])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- servidor

def handler_factory(db_path: Path, static_dir: Path = ROOT):
    limiter = AttemptLimiter()
    # Arquivos abertos sem login (a tela de entrada precisa deles).
    public_files = {
        "/login": ("login.html", "text/html; charset=utf-8"),
        "/login.js": ("login.js", "text/javascript; charset=utf-8"),
        "/styles.css": ("styles.css", "text/css; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = f"AgendaAcademica/{VERSION}"

        # ---- respostas
        def send_bytes(self, status: HTTPStatus, content: bytes, media_type: str, headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":  # HEAD recebe só os cabeçalhos
                self.wfile.write(content)

        def send_json(self, status: HTTPStatus, payload: object, headers: dict | None = None) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_bytes(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store", **(headers or {})})

        def send_file(self, filename: str, media_type: str) -> None:
            self.send_bytes(HTTPStatus.OK, (static_dir / filename).read_bytes(), media_type, {"Cache-Control": "no-cache"})

        def redirect(self, location: str) -> None:
            self.send_bytes(HTTPStatus.SEE_OTHER, b"", "text/plain; charset=utf-8", {"Location": location})

        def read_json(self) -> object:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                raise ValueError("Envie os dados em formato JSON.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Tamanho da requisição inválido.") from exc
            if length < 1 or length > 4096:
                raise ValueError("O conteúdo enviado está vazio ou é muito grande.")
            try:
                return json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("JSON inválido.") from exc

        # ---- sessão
        def session_token(self) -> str:
            try:
                morsel = SimpleCookie(self.headers.get("Cookie", "")).get(SESSION_COOKIE)
            except CookieError:
                return ""
            return morsel.value if morsel else ""

        def current_user(self) -> sqlite3.Row | None:
            token = self.session_token()
            if not token:
                return None
            with connect(db_path) as connection:
                return connection.execute(
                    "SELECT users.id, users.name, users.username FROM sessions JOIN users ON users.id = sessions.user_id "
                    "WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
                    (token_digest(token), utc_now()),
                ).fetchone()

        def session_cookie(self, token: str, max_age: int) -> str:
            # HttpOnly: o JavaScript da página não lê o cookie. SameSite=Lax: outros sites não enviam pedidos com ele.
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "") == "https" else ""
            return f"{SESSION_COOKIE}={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax{secure}"

        def start_session(self, connection: sqlite3.Connection, user_id: int) -> str:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + SESSION_DURATION).isoformat(timespec="seconds")
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (utc_now(),))
            connection.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                               (token_digest(token), user_id, expires))
            return self.session_cookie(token, int(SESSION_DURATION.total_seconds()))

        # ---- rotas
        def task_id(self) -> int | None:
            match = re.fullmatch(r"/api/tasks/([1-9]\d*)", urlsplit(self.path).path)
            return int(match.group(1)) if match else None

        def user_tasks(self, user_id: int) -> list[sqlite3.Row]:
            with connect(db_path) as connection:
                return connection.execute(f"SELECT * FROM tasks WHERE user_id = ? {ORDER_BY}", (user_id,)).fetchall()

        def require_user(self) -> sqlite3.Row | None:
            user = self.current_user()
            if user is None:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Faça login para continuar."})
            return user

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/health":
                self.send_json(HTTPStatus.OK, {"status": "ok", "version": VERSION})
                return
            if path == "/login" and self.current_user():
                self.redirect("/")
                return
            if path in public_files:
                self.send_file(*public_files[path])
                return
            if path == "/":
                if self.current_user() is None:
                    self.redirect("/login")
                else:
                    self.send_file("index.html", "text/html; charset=utf-8")
                return
            if not path.startswith("/api/"):
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Página não encontrada."})
                return
            user = self.require_user()
            if user is None:
                return
            if path == "/api/me":
                self.send_json(HTTPStatus.OK, {"user": public_user(user)})
            elif path == "/api/tasks":
                self.send_json(HTTPStatus.OK, {"tasks": [serialize(row) for row in self.user_tasks(user["id"])]})
            elif path == "/api/tasks/export.csv":
                filename = f"agenda-academica-{date.today().isoformat()}.csv"
                self.send_bytes(HTTPStatus.OK, tasks_to_csv(self.user_tasks(user["id"])), "text/csv; charset=utf-8", {
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                })
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Página não encontrada."})

        def do_HEAD(self) -> None:
            """Mesma resposta do GET, sem o conteúdo (usado por verificações automáticas da hospedagem)."""
            self.do_GET()

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/logout":
                self.logout()
                return
            account_routes = {
                "/api/register": self.register,
                "/api/login": self.login,
                "/api/password/question": self.password_question,
                "/api/password/reset": self.password_reset,
            }
            if path not in account_routes and path != "/api/tasks":
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada."})
                return
            user = None
            if path == "/api/tasks":
                user = self.require_user()
                if user is None:
                    return
            try:
                payload = self.read_json()
            except ValueError as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if path in account_routes:
                account_routes[path](payload)
                return
            task, error = validate_task(payload)
            if error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": error})
                return
            now = utc_now()
            with connect(db_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO tasks (title, subject, due_date, due_time, notes, completed, priority, user_id, created_at, updated_at) "
                    "VALUES (:title, :subject, :due_date, :due_time, :notes, :completed, :priority, :user_id, :now, :now)",
                    {**task, "user_id": user["id"], "now": now},
                )
                row = connection.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
            self.send_json(HTTPStatus.CREATED, {"task": serialize(row)})

        def do_PUT(self) -> None:
            user = self.require_user()
            if user is None:
                return
            task_id = self.task_id()
            if task_id is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            try:
                payload = self.read_json()
            except ValueError as exc:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            task, error = validate_task(payload)
            if error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": error})
                return
            with connect(db_path) as connection:
                # "AND user_id" garante que ninguém altera a tarefa de outra conta, mesmo sabendo o número dela.
                cursor = connection.execute(
                    "UPDATE tasks SET title=:title, subject=:subject, due_date=:due_date, due_time=:due_time, notes=:notes, "
                    "completed=:completed, priority=:priority, updated_at=:now WHERE id=:id AND user_id=:user_id",
                    {**task, "now": utc_now(), "id": task_id, "user_id": user["id"]},
                )
                row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone() if cursor.rowcount else None
            if row is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            self.send_json(HTTPStatus.OK, {"task": serialize(row)})

        def do_DELETE(self) -> None:
            user = self.require_user()
            if user is None:
                return
            task_id = self.task_id()
            if task_id is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            with connect(db_path) as connection:
                cursor = connection.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, user["id"]))
            if cursor.rowcount == 0:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            self.send_json(HTTPStatus.OK, {"deleted": True})

        # ---- contas
        def register(self, payload: object) -> None:
            account, error = validate_account(payload)
            if error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": error})
                return
            try:
                with connect(db_path) as connection:
                    user_id = connection.execute(
                        "INSERT INTO users (name, username, password_hash, question, answer_hash, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (account["name"], account["username"], hash_secret(account["password"]), account["question"],
                         hash_secret(normalize_answer(account["answer"])), utc_now()),
                    ).lastrowid
                    adopt_orphan_tasks(connection, user_id)
                    cookie = self.start_session(connection, user_id)
            except sqlite3.IntegrityError:
                self.send_json(HTTPStatus.CONFLICT, {"error": "Este usuário já está em uso. Escolha outro."})
                return
            self.send_json(HTTPStatus.CREATED, {"user": {"name": account["name"], "username": account["username"]}},
                           {"Set-Cookie": cookie})

        def login(self, payload: object) -> None:
            data = payload if isinstance(payload, dict) else {}
            username = normalize_username(data.get("username"))
            password = data.get("password") if isinstance(data.get("password"), str) else ""
            key = f"login:{username}"
            if limiter.blocked(key):
                self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": TOO_MANY_ATTEMPTS})
                return
            with connect(db_path) as connection:
                user = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                if user is None or not check_secret(password, user["password_hash"]):
                    limiter.failed(key)
                    self.log_message("Login recusado para o usuário %r.", username)
                    # Mesma mensagem nos dois casos: não revela se o usuário existe.
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Usuário ou senha incorretos."})
                    return
                limiter.reset(key)
                cookie = self.start_session(connection, user["id"])
            self.send_json(HTTPStatus.OK, {"user": public_user(user)}, {"Set-Cookie": cookie})

        def logout(self) -> None:
            token = self.session_token()
            if token:
                with connect(db_path) as connection:
                    connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))
            self.send_json(HTTPStatus.OK, {"logged_out": True}, {"Set-Cookie": self.session_cookie("", 0)})

        def account_for_recovery(self, payload: object) -> tuple[sqlite3.Row | None, dict]:
            data = payload if isinstance(payload, dict) else {}
            with connect(db_path) as connection:
                user = connection.execute("SELECT * FROM users WHERE username = ?",
                                          (normalize_username(data.get("username")),)).fetchone()
            if user is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Usuário não encontrado. Confira como ele foi escrito."})
            elif not user["question"]:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Esta conta não tem pergunta secreta. A senha só pode ser trocada pelo administrador."})
                user = None
            return user, data

        def password_question(self, payload: object) -> None:
            user, _ = self.account_for_recovery(payload)
            if user is not None:
                self.send_json(HTTPStatus.OK, {"question": user["question"]})

        def password_reset(self, payload: object) -> None:
            user, data = self.account_for_recovery(payload)
            if user is None:
                return
            key = f"reset:{user['username']}"
            if limiter.blocked(key):
                self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": TOO_MANY_ATTEMPTS})
                return
            error = password_error(data.get("new_password"))
            if error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": error})
                return
            answer = data.get("answer") if isinstance(data.get("answer"), str) else ""
            if not check_secret(normalize_answer(answer), user["answer_hash"]):
                limiter.failed(key)
                self.log_message("Resposta secreta incorreta para o usuário %r.", user["username"])
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Resposta incorreta."})
                return
            limiter.reset(key, f"login:{user['username']}")
            with connect(db_path) as connection:
                connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_secret(data["new_password"]), user["id"]))
                # Sai de todos os aparelhos em que a conta estava aberta.
                connection.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
                cookie = self.start_session(connection, user["id"])
            self.send_json(HTTPStatus.OK, {"user": public_user(user)}, {"Set-Cookie": cookie})

    return Handler


def create_server(db_path: Path, host: str, port: int) -> ThreadingHTTPServer:
    """Abre o servidor e troca o erro técnico de porta ocupada por uma orientação em português."""
    try:
        return ThreadingHTTPServer((host, port), handler_factory(db_path))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit(
                f"A porta {port} já está em uso. Feche a outra janela da Agenda Acadêmica "
                f"ou escolha outra porta, por exemplo: PORT={port + 1} python3 app.py"
            ) from None
        raise


def local_network_address() -> str | None:
    """Descobre o IP do computador na rede local, usado para abrir a agenda no celular."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))  # UDP não envia nada; só consulta a rota padrão (o Wi-Fi).
            return probe.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    db_path = Path(os.environ.get("AGENDA_DB_PATH", ROOT / "data" / "agenda.db"))
    # 127.0.0.1 = só este computador; HOST=0.0.0.0 libera o acesso pela rede e na hospedagem.
    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        raise SystemExit("A variável PORT deve conter apenas números, por exemplo: PORT=8000") from None
    # Na hospedagem, AGENDA_USUARIO e AGENDA_SENHA criam a conta do avaliador (o disco do plano gratuito é apagado
    # a cada reinício, então a conta é recriada sempre que o servidor sobe).
    # strip: ignora espaços e aspas que costumam vir junto ao colar o valor no painel da hospedagem.
    username = os.environ.get("AGENDA_USUARIO", "avaliador").strip().strip("\"'`").strip() or "avaliador"
    password = os.environ.get("AGENDA_SENHA", "").strip().strip("\"'`").strip()
    server = create_server(db_path, host, port)
    first_run = not db_path.exists()
    initialize(db_path)
    if first_run:
        seed_project_plan(db_path)
    if password:
        ensure_account(db_path, username, password)
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "")  # o Render informa o endereço público do serviço
    if public_url:
        print(f"Agenda Acadêmica {VERSION} publicada em {public_url}", flush=True)
    else:
        print(f"Agenda Acadêmica {VERSION}: http://127.0.0.1:{server.server_port}", flush=True)
    if password:
        print(f"Conta de acesso pronta (usuário: {normalize_username(username)}; senha com {len(password)} caracteres).", flush=True)
    elif public_url:
        print("AGENDA_SENHA não definida: a agenda funciona, mas a conta do avaliador não foi criada.", flush=True)
    if host == "0.0.0.0" and not public_url:
        address = local_network_address()
        if address:
            print(f"Na mesma rede Wi-Fi (ex.: celular): http://{address}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
