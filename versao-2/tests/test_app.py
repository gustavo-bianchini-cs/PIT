"""Testes de integração da API (versão 2.0) usando um banco de dados temporário."""

import base64
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import connect, create_server, handler_factory, initialize, seed_project_plan


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "agenda.db"
        initialize(self.db_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.db_path))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def request(self, path, method="GET", data=None):
        payload = json.dumps(data).encode() if data is not None else None
        request = Request(
            self.base + path,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"} if payload is not None else {},
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_create_edit_complete_reopen_delete_and_persist(self):
        task = {"title": "Estudar matemática", "subject": "Matemática", "due_date": "2026-11-20",
                "notes": "Capítulo 3", "completed": False, "priority": "alta"}
        status, result = self.request("/api/tasks", "POST", task)
        self.assertEqual(status, 201)
        task_id = result["task"]["id"]
        self.assertFalse(result["task"]["completed"])
        self.assertEqual(result["task"]["priority"], "alta")

        status, result = self.request("/api/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["title"], task["title"])

        updated = {**task, "title": "Revisar matemática", "completed": True, "priority": "baixa"}
        status, result = self.request(f"/api/tasks/{task_id}", "PUT", updated)
        self.assertEqual(status, 200)
        self.assertEqual(result["task"]["title"], updated["title"])
        self.assertTrue(result["task"]["completed"])
        self.assertEqual(result["task"]["priority"], "baixa")

        status, result = self.request(f"/api/tasks/{task_id}", "PUT", {**updated, "completed": False})
        self.assertEqual(status, 200)
        self.assertFalse(result["task"]["completed"])

        # Abre o mesmo banco em outra conexão para verificar a gravação real.
        with connect(self.db_path) as connection:
            saved = connection.execute("SELECT title, completed, priority FROM tasks WHERE id=?", (task_id,)).fetchone()
        self.assertEqual(tuple(saved), ("Revisar matemática", 0, "baixa"))

        status, result = self.request(f"/api/tasks/{task_id}", "DELETE")
        self.assertEqual((status, result), (200, {"deleted": True}))
        self.assertEqual(self.request("/api/tasks")[1]["tasks"], [])

    def test_priority_is_optional_and_validated(self):
        base = {"title": "Prova", "subject": "Física", "due_date": "2026-12-01"}
        status, result = self.request("/api/tasks", "POST", base)
        self.assertEqual(status, 201)
        self.assertEqual(result["task"]["priority"], "media")
        for invalid in ("urgente", "", None, 3):
            with self.subTest(priority=invalid):
                status, result = self.request("/api/tasks", "POST", {**base, "priority": invalid})
                self.assertEqual(status, 400)
                self.assertIn("prioridade", result["error"])

    def test_list_orders_pending_by_due_date_then_priority(self):
        tasks = [
            ("Concluída", "2026-11-01", "alta", True),
            ("Mesmo dia, baixa", "2026-11-20", "baixa", False),
            ("Mesmo dia, alta", "2026-11-20", "alta", False),
            ("Prazo antes", "2026-11-18", "baixa", False),
        ]
        for title, due, priority, completed in tasks:
            self.request("/api/tasks", "POST", {"title": title, "subject": "Geral", "due_date": due,
                                                "priority": priority, "completed": completed})
        titles = [task["title"] for task in self.request("/api/tasks")[1]["tasks"]]
        self.assertEqual(titles, ["Prazo antes", "Mesmo dia, alta", "Mesmo dia, baixa", "Concluída"])

    def test_export_csv_for_spreadsheets(self):
        self.request("/api/tasks", "POST", {"title": "Relatório; parte 2", "subject": "Química", "due_date": "2026-11-25",
                                            "notes": "Levar \"jaleco\"", "priority": "alta"})
        self.request("/api/tasks", "POST", {"title": "=SOMA(A1:A2)", "subject": "Planilhas", "due_date": "2026-11-26",
                                            "completed": True})
        with urlopen(self.base + "/api/tasks/export.csv", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/csv", response.headers["Content-Type"])
            self.assertIn("attachment", response.headers["Content-Disposition"])
            raw = response.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "o arquivo deve ter BOM para o Excel reconhecer os acentos")
        lines = raw.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "ID;Título;Disciplina;Prioridade;Data de entrega;Situação;Observações")
        self.assertEqual(lines[1], '1;"Relatório; parte 2";Química;Alta;25/11/2026;Pendente;"Levar ""jaleco"""')
        self.assertEqual(lines[2], "2;'=SOMA(A1:A2);Planilhas;Média;26/11/2026;Concluída;")

    def test_rejects_invalid_data_and_unknown_task(self):
        base = {"title": "A", "subject": "B", "due_date": "2026-11-20", "completed": False}
        cases = [
            {**base, "title": "   "},
            {**base, "subject": ""},
            {**base, "due_date": "2026-02-30"},
            {**base, "completed": "sim"},
            {**base, "notes": "x" * 501},
        ]
        for case in cases:
            with self.subTest(case=case):
                status, result = self.request("/api/tasks", "POST", case)
                self.assertEqual(status, 400)
                self.assertIn("error", result)
        self.assertEqual(self.request("/api/tasks")[1]["tasks"], [])
        self.assertEqual(self.request("/api/tasks/999", "PUT", base)[0], 404)
        self.assertEqual(self.request("/api/tasks/999", "DELETE")[0], 404)

    def test_page_health_and_missing_route(self):
        with urlopen(self.base + "/", timeout=3) as response:
            self.assertEqual(response.status, 200)
            page = response.read().decode()
            self.assertIn("Agenda Acadêmica", page)
            self.assertIn('id="search"', page)
        for path, expected in [("/styles.css", "text/css"), ("/app.js", "text/javascript")]:
            with urlopen(self.base + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(expected, response.headers["Content-Type"])
                self.assertGreater(len(response.read()), 100)
        self.assertEqual(self.request("/health"), (200, {"status": "ok", "version": "2.1"}))
        self.assertEqual(self.request("/api/unknown")[0], 404)

    def test_project_plan_only_populates_an_empty_database(self):
        self.assertEqual(seed_project_plan(self.db_path, date(2026, 11, 8)), 10)
        self.assertEqual(seed_project_plan(self.db_path, date(2026, 11, 8)), 0)
        tasks = self.request("/api/tasks")[1]["tasks"]
        self.assertEqual(len(tasks), 10)
        self.assertEqual(sum(task["completed"] for task in tasks), 4)
        self.assertTrue(any(task["title"] == "Revisar a documentação com a PIT I" for task in tasks))
        self.assertTrue(all(task["priority"] in ("baixa", "media", "alta") for task in tasks))


class MigrationTests(unittest.TestCase):
    def test_database_from_version_1_receives_priority_column(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "agenda.db"
            # Estrutura exatamente como a versão 1.0 criava a tabela.
            connection = sqlite3.connect(db_path)
            connection.executescript("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, subject TEXT NOT NULL,
                    due_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                INSERT INTO tasks (title, subject, due_date, notes, completed, created_at, updated_at)
                VALUES ('Tarefa antiga', 'História', '2026-11-10', '', 0, 'x', 'x');
            """)
            connection.close()

            initialize(db_path)
            initialize(db_path)  # rodar de novo não deve dar erro nem duplicar a coluna

            with connect(db_path) as connection:
                columns = [row["name"] for row in connection.execute("PRAGMA table_info(tasks)")]
                row = connection.execute("SELECT title, priority FROM tasks").fetchone()
            self.assertEqual(columns.count("priority"), 1)
            self.assertEqual(tuple(row), ("Tarefa antiga", "media"))


class PasswordTests(unittest.TestCase):
    """Versão publicada: com senha definida, páginas e API pedem usuário e senha."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name) / "agenda.db"
        initialize(db_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(db_path, username="avaliador", password="s3nha-de-teste"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def call(self, path, credentials=None, method="GET", data=None):
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if credentials:
            headers["Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode()
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    def test_requires_user_and_password(self):
        for path in ("/", "/app.js", "/api/tasks", "/api/tasks/export.csv"):
            with self.subTest(path=path):
                status, headers, body = self.call(path)
                self.assertEqual(status, 401)
                self.assertIn('Basic realm="Agenda Academica"', headers["WWW-Authenticate"])
                self.assertIn("Acesso restrito", body.decode())
        for wrong in ("avaliador:errada", "outro:s3nha-de-teste", "avaliador:", "sem-dois-pontos"):
            with self.subTest(credentials=wrong):
                self.assertEqual(self.call("/api/tasks", wrong)[0], 401)
        task = {"title": "Prova", "subject": "Física", "due_date": "2026-12-01"}
        self.assertEqual(self.call("/api/tasks", None, "POST", task)[0], 401)
        self.assertEqual(self.call("/api/tasks", "avaliador:s3nha-de-teste")[0], 200)
        self.assertEqual(self.call("/", "avaliador:s3nha-de-teste")[0], 200)
        self.assertEqual(self.call("/api/tasks", "avaliador:s3nha-de-teste", "POST", task)[0], 201)

    def test_health_stays_open_for_hosting(self):
        status, _, body = self.call("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")


class ServerStartTests(unittest.TestCase):
    def test_busy_port_shows_message_in_portuguese(self):
        with tempfile.TemporaryDirectory() as tempdir, socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            with self.assertRaises(SystemExit) as context:
                create_server(Path(tempdir) / "agenda.db", "127.0.0.1", port)
        self.assertIn(f"A porta {port} já está em uso", str(context.exception.code))


if __name__ == "__main__":
    unittest.main()
