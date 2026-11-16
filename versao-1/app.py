"""Servidor local e API da Agenda Acadêmica (Python 3, sem dependências)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    due_date TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


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


def initialize(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)


def seed_project_plan(db_path: Path, today: date | None = None) -> int:
    """Cria um plano inicial da PIT somente em um banco novo e vazio."""
    today = today or date.today()
    plan = [
        ("Consolidar a documentação da Agenda Acadêmica", "PIT · Documentação", 0, True,
         "Objetivo, requisitos RF01–RF07, regras, fluxo e arquitetura Python/SQLite reunidos em DOCUMENTACAO_PROJETO.md."),
        ("Preencher os dados técnicos no formulário PIT", "PIT · Entrega", 0, True,
         "Back-end Python 3, banco SQLite, plataforma web e modo tradicional registrados em PIT_atividade_preenchida.docx. Nome, RGM e links ainda faltam."),
        ("Executar os testes locais e registrar correções", "PIT · Qualidade", 0, True,
         "Testes de integração aprovados; a correção do fechamento da conexão SQLite está descrita em LAUDO_QUALIDADE.md."),
        ("Preparar o roteiro do vídeo narrado", "PIT · Vídeo", 0, True,
         "Roteiro de cerca de 5min40 em ROTEIROS_DE_VIDEO.md: objetivo, cadastro, filtros, edição, persistência, código e laudo."),
        ("Revisar a documentação com a PIT I", "PIT · Documentação", 2, False,
         "Comparar a documentação atual com a versão da PIT I e com o material teórico da disciplina; ajustar pontos ausentes."),
        ("Realizar cinco testes com participantes", "PIT · Testes", 3, False,
         "Convidar cinco pessoas disponíveis ou confirmar uma alternativa com o professor. Registrar data e resultado depois de cada teste."),
        ("Gravar o vídeo narrado da aplicação", "PIT · Vídeo", 5, False,
         "Vídeo de no mínimo 5min. Demonstrar cadastro, edição, conclusão, filtros e persistência; conferir o link depois do envio."),
        ("Criar repositório e publicar a aplicação", "PIT · Publicação", 7, False,
         "Criar a conta GitHub, enviar código e documentação e obter um endereço público para a aplicação."),
        ("Preencher nome, RGM e links finais da PIT", "PIT · Entrega", 9, False,
         "Conferir dados pessoais, endereço do repositório, link da aplicação e vídeos antes de enviar o formulário."),
        ("Gravar o vídeo das correções após feedback", "PIT · Vídeo", 10, False,
         "Vídeo de até 5min com problema observado, alteração realizada e reteste. Depende das avaliações e correções pertinentes."),
    ]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect(db_path) as connection:
        if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] != 0:
            return 0
        connection.executemany(
            "INSERT INTO tasks (title, subject, due_date, notes, completed, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(title, subject, (today + timedelta(days=days)).isoformat(), notes,
              int(completed), now, now)
             for title, subject, days, completed, notes in plan],
        )
    return len(plan)


def validate_task(data: object) -> tuple[dict | None, str | None]:
    if not isinstance(data, dict):
        return None, "Envie um objeto JSON válido."
    title = data.get("title")
    subject = data.get("subject")
    due_date = data.get("due_date")
    notes = data.get("notes", "")
    completed = data.get("completed", False)
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
    if not isinstance(notes, str) or len(notes) > 500:
        return None, "As observações devem ter até 500 caracteres."
    if not isinstance(completed, bool):
        return None, "O estado da tarefa deve ser verdadeiro ou falso."
    return {
        "title": title.strip(),
        "subject": subject.strip(),
        "due_date": due_date,
        "notes": notes.strip(),
        "completed": int(completed),
    }, None


def serialize(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["completed"] = bool(item["completed"])
    return item


def handler_factory(db_path: Path, static_dir: Path = ROOT):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AgendaAcademica/1.0"

        def send_json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_file(self, filename: str, media_type: str) -> None:
            content = (static_dir / filename).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

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

        def do_GET(self) -> None:
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
                self.send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if path == "/api/tasks":
                with connect(db_path) as connection:
                    rows = connection.execute(
                        "SELECT * FROM tasks ORDER BY completed ASC, due_date ASC, id DESC"
                    ).fetchall()
                self.send_json(HTTPStatus.OK, {"tasks": [serialize(row) for row in rows]})
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Página não encontrada."})

        def do_POST(self) -> None:
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
                    "INSERT INTO tasks (title, subject, due_date, notes, completed, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (*task.values(), now, now),
                )
                row = connection.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
            self.send_json(HTTPStatus.CREATED, {"task": serialize(row)})

        def do_PUT(self) -> None:
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
                    "UPDATE tasks SET title=?, subject=?, due_date=?, notes=?, completed=?, updated_at=? "
                    "WHERE id=?",
                    (*task.values(), now, task_id),
                )
                row = connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone() if cursor.rowcount else None
            if row is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Tarefa não encontrada."})
                return
            self.send_json(HTTPStatus.OK, {"task": serialize(row)})

        def do_DELETE(self) -> None:
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


def main() -> None:
    db_path = Path(os.environ.get("AGENDA_DB_PATH", ROOT / "data" / "agenda.db"))
    port = int(os.environ.get("PORT", "8000"))
    first_run = not db_path.exists()
    initialize(db_path)
    if first_run:
        seed_project_plan(db_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_factory(db_path))
    print(f"Agenda Acadêmica: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
