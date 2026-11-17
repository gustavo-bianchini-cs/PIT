"""Servidor e API da Agenda Acadêmica — versão 2.2 (Python 3, sem dependências)."""

from __future__ import annotations

import base64
import csv
import errno
import io
import json
import os
import re
import secrets
import socket
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


VERSION = "2.2"
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
# Horário vazio = o prazo vale até o fim do dia.
END_OF_DAY = "23:59"
# Pendentes primeiro, depois o prazo mais próximo (data e horário) e, no mesmo prazo, a prioridade mais alta.
ORDER_BY = (
    f"ORDER BY completed ASC, due_date ASC, CASE due_time WHEN '' THEN '{END_OF_DAY}' ELSE due_time END ASC, "
    "CASE priority WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END, id DESC"
)


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
    """Atualiza bancos de versões anteriores: a 1.0 não tinha prioridade e a 2.1 não tinha horário de entrega."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
    if "priority" not in columns:
        connection.execute(
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'media' "
            "CHECK (priority IN ('baixa', 'media', 'alta'))"
        )
    if "due_time" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN due_time TEXT NOT NULL DEFAULT ''")


def initialize(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        migrate(connection)


def seed_project_plan(db_path: Path, today: date | None = None) -> int:
    """Cria um plano inicial da PIT somente em um banco novo e vazio."""
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
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
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


def serialize(row: sqlite3.Row) -> dict:
    item = dict(row)
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


def handler_factory(db_path: Path, static_dir: Path = ROOT, username: str = "avaliador", password: str = ""):
    """Com password definida (versão publicada), todas as páginas pedem usuário e senha."""
    class Handler(BaseHTTPRequestHandler):
        server_version = f"AgendaAcademica/{VERSION}"

        def authorized(self) -> bool:
            if not password:
                return True
            scheme, _, encoded = self.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "basic":
                return False
            try:
                user, _, given = base64.b64decode(encoded, validate=True).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                return False
            # compare_digest compara em tempo constante: não revela quantos caracteres estão certos.
            ok = secrets.compare_digest(user.encode(), username.encode()) & secrets.compare_digest(given.encode(), password.encode())
            if not ok:  # registra só o tamanho da senha, nunca o conteúdo
                self.log_message("Login recusado: usuário %r (esperado %r); senha recebida com %d caracteres (a configurada tem %d).",
                                 user, username, len(given), len(password))
            return ok

        def login_required(self) -> bool:
            """Responde 401 (o navegador abre a janela de usuário e senha). /health fica livre para a hospedagem."""
            if urlsplit(self.path).path == "/health" or self.authorized():
                return False
            body = "Acesso restrito: informe o usuário e a senha da Agenda Acadêmica.".encode("utf-8")
            self.send_bytes(HTTPStatus.UNAUTHORIZED, body, "text/plain; charset=utf-8",
                            {"WWW-Authenticate": 'Basic realm="Agenda Academica", charset="UTF-8"'})
            return True

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

        def send_json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_bytes(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

        def send_file(self, filename: str, media_type: str) -> None:
            self.send_bytes(HTTPStatus.OK, (static_dir / filename).read_bytes(), media_type)

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

        def task_id(self) -> int | None:
            match = re.fullmatch(r"/api/tasks/([1-9]\d*)", urlsplit(self.path).path)
            return int(match.group(1)) if match else None

        def all_tasks(self) -> list[sqlite3.Row]:
            with connect(db_path) as connection:
                return connection.execute(f"SELECT * FROM tasks {ORDER_BY}").fetchall()

        def do_GET(self) -> None:
            if self.login_required():
                return
            path = urlsplit(self.path).path
            static = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            }
            if path in static:
                self.send_file(*static[path])
                return
            if path == "/health":
                self.send_json(HTTPStatus.OK, {"status": "ok", "version": VERSION})
                return
            if path == "/api/tasks":
                self.send_json(HTTPStatus.OK, {"tasks": [serialize(row) for row in self.all_tasks()]})
                return
            if path == "/api/tasks/export.csv":
                filename = f"agenda-academica-{date.today().isoformat()}.csv"
                self.send_bytes(HTTPStatus.OK, tasks_to_csv(self.all_tasks()), "text/csv; charset=utf-8", {
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                })
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Página não encontrada."})

        def do_HEAD(self) -> None:
            """Mesma resposta do GET, sem o conteúdo (usado por verificações automáticas da hospedagem)."""
            self.do_GET()

        def do_POST(self) -> None:
            if self.login_required():
                return
            if urlsplit(self.path).path != "/api/tasks":
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada."})
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
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with connect(db_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO tasks (title, subject, due_date, due_time, notes, completed, priority, created_at, updated_at) "
                    "VALUES (:title, :subject, :due_date, :due_time, :notes, :completed, :priority, :now, :now)",
                    {**task, "now": now},
                )
                row = connection.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
            self.send_json(HTTPStatus.CREATED, {"task": serialize(row)})

        def do_PUT(self) -> None:
            if self.login_required():
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
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with connect(db_path) as connection:
                cursor = connection.execute(
                    "UPDATE tasks SET title=:title, subject=:subject, due_date=:due_date, due_time=:due_time, notes=:notes, "
                    "completed=:completed, priority=:priority, updated_at=:now WHERE id=:id",
                    {**task, "now": now, "id": task_id},
                )
                row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone() if cursor.rowcount else None
            if row is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            self.send_json(HTTPStatus.OK, {"task": serialize(row)})

        def do_DELETE(self) -> None:
            if self.login_required():
                return
            task_id = self.task_id()
            if task_id is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            with connect(db_path) as connection:
                cursor = connection.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            if cursor.rowcount == 0:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            self.send_json(HTTPStatus.OK, {"deleted": True})

    return Handler


def create_server(db_path: Path, host: str, port: int, username: str = "avaliador", password: str = "") -> ThreadingHTTPServer:
    """Abre o servidor e troca o erro técnico de porta ocupada por uma orientação em português."""
    try:
        return ThreadingHTTPServer((host, port), handler_factory(db_path, username=username, password=password))
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
    # Na hospedagem, AGENDA_SENHA protege o acesso; rodando no próprio computador, não é preciso definir.
    # strip: ignora espaços e aspas que costumam vir junto ao colar o valor no painel da hospedagem.
    username = os.environ.get("AGENDA_USUARIO", "avaliador").strip().strip("\"'`").strip() or "avaliador"
    password = os.environ.get("AGENDA_SENHA", "").strip().strip("\"'`").strip()
    server = create_server(db_path, host, port, username, password)
    first_run = not db_path.exists()
    initialize(db_path)
    if first_run:
        seed_project_plan(db_path)
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "")  # o Render informa o endereço público do serviço
    if public_url:
        print(f"Agenda Acadêmica {VERSION} publicada em {public_url}", flush=True)
    else:
        print(f"Agenda Acadêmica {VERSION}: http://127.0.0.1:{server.server_port}", flush=True)
    if password:
        print(f"Acesso protegido por senha (usuário: {username}; senha com {len(password)} caracteres).", flush=True)
    elif public_url:
        print("ATENÇÃO: AGENDA_SENHA não definida; qualquer pessoa com o link pode alterar a lista.", flush=True)
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
