"""Testes de integração da API (versão 2) usando um banco de dados temporário."""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from app import connect, create_server, ensure_account, handler_factory, initialize, seed_project_plan

ANA = {"name": "Ana Souza", "username": "ana.souza", "password": "senha-da-ana",
       "question": "Qual o nome da minha primeira professora?", "answer": "Dona Cecília"}


class NoRedirect(HTTPRedirectHandler):
    """Deixa o teste ver o redirecionamento (303) em vez de segui-lo."""

    def redirect_request(self, *args, **kwargs):
        return None


class ServerTestCase(unittest.TestCase):
    """Sobe o servidor com um banco temporário; cada teste usa contas próprias."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "agenda.db"
        initialize(self.db_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.db_path))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.cookie = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def raw(self, path, method="GET", data=None, cookie=None):
        """Faz a requisição e devolve (status, cabeçalhos, corpo em bytes)."""
        headers = {"Content-Type": "application/json"} if data is not None else {}
        cookie = self.cookie if cookie is None else cookie
        if cookie:
            headers["Cookie"] = cookie
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                          method=method, headers=headers)
        try:
            with build_opener(NoRedirect).open(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            with error:
                return error.code, error.headers, error.read()

    def request(self, path, method="GET", data=None, cookie=None):
        status, _, body = self.raw(path, method, data, cookie)
        return status, json.loads(body)

    def register(self, account=ANA):
        """Cria a conta e guarda o cookie da sessão para as próximas requisições."""
        status, headers, body = self.raw("/api/register", "POST", account, cookie="")
        self.assertEqual(status, 201, body)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        return self.cookie


class TaskTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.register()

    def test_create_edit_complete_reopen_delete_and_persist(self):
        task = {"title": "Estudar matemática", "subject": "Matemática", "due_date": "2026-11-20",
                "notes": "Capítulo 3", "completed": False, "priority": "alta"}
        status, result = self.request("/api/tasks", "POST", task)
        self.assertEqual(status, 201)
        task_id = result["task"]["id"]
        self.assertFalse(result["task"]["completed"])
        self.assertEqual(result["task"]["priority"], "alta")
        self.assertNotIn("user_id", result["task"])

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

    def test_due_time_is_optional_and_validated(self):
        base = {"title": "Entrega do relatório", "subject": "Química", "due_date": "2026-11-25"}
        status, result = self.request("/api/tasks", "POST", base)
        self.assertEqual((status, result["task"]["due_time"]), (201, ""))
        status, result = self.request("/api/tasks", "POST", {**base, "due_time": "14:30"})
        self.assertEqual((status, result["task"]["due_time"]), (201, "14:30"))
        task_id = result["task"]["id"]
        status, result = self.request(f"/api/tasks/{task_id}", "PUT", {**base, "due_time": "08:05"})
        self.assertEqual((status, result["task"]["due_time"]), (200, "08:05"))
        for invalid in ("24:00", "9:00", "14h30", "14:60", "14:30:00", None, 1430):
            with self.subTest(due_time=invalid):
                status, result = self.request("/api/tasks", "POST", {**base, "due_time": invalid})
                self.assertEqual(status, 400)
                self.assertIn("horário", result["error"])

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

    def test_same_day_tasks_are_ordered_by_time(self):
        tasks = [
            ("Sem horário, alta", "", "alta"),
            ("Às 18h, baixa", "18:00", "baixa"),
            ("Às 08h, baixa", "08:00", "baixa"),
            ("Às 18h, alta", "18:00", "alta"),
        ]
        for title, due_time, priority in tasks:
            self.request("/api/tasks", "POST", {"title": title, "subject": "Geral", "due_date": "2026-11-20",
                                                "due_time": due_time, "priority": priority})
        titles = [task["title"] for task in self.request("/api/tasks")[1]["tasks"]]
        # sem horário = até 23:59, por isso fica por último mesmo com prioridade alta
        self.assertEqual(titles, ["Às 08h, baixa", "Às 18h, alta", "Às 18h, baixa", "Sem horário, alta"])

    def test_export_csv_for_spreadsheets(self):
        self.request("/api/tasks", "POST", {"title": "Relatório; parte 2", "subject": "Química", "due_date": "2026-11-25",
                                            "due_time": "14:30", "notes": "Levar \"jaleco\"", "priority": "alta"})
        self.request("/api/tasks", "POST", {"title": "=SOMA(A1:A2)", "subject": "Planilhas", "due_date": "2026-11-26",
                                            "completed": True})
        status, headers, raw = self.raw("/api/tasks/export.csv")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers["Content-Type"])
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "o arquivo deve ter BOM para o Excel reconhecer os acentos")
        lines = raw.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "ID;Título;Disciplina;Prioridade;Data de entrega;Horário;Situação;Observações")
        self.assertEqual(lines[1], '1;"Relatório; parte 2";Química;Alta;25/11/2026;14:30;Pendente;"Levar ""jaleco"""')
        self.assertEqual(lines[2], "2;'=SOMA(A1:A2);Planilhas;Média;26/11/2026;;Concluída;")

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
        status, _, page = self.raw("/")
        self.assertEqual(status, 200)
        self.assertIn("Agenda Acadêmica", page.decode())
        self.assertIn('id="search"', page.decode())
        for path, expected in [("/styles.css", "text/css"), ("/app.js", "text/javascript"), ("/login.js", "text/javascript")]:
            status, headers, body = self.raw(path)
            self.assertEqual(status, 200)
            self.assertIn(expected, headers["Content-Type"])
            self.assertGreater(len(body), 100)
        self.assertEqual(self.request("/health"), (200, {"status": "ok", "version": "2.3"}))
        self.assertEqual(self.request("/api/unknown")[0], 404)

    def test_head_returns_headers_without_body(self):
        status, headers, body = self.raw("/", method="HEAD")
        self.assertEqual(status, 200)
        self.assertGreater(int(headers["Content-Length"]), 100)
        self.assertEqual(body, b"")


class AccountTests(ServerTestCase):
    def test_pages_and_api_require_login(self):
        status, headers, _ = self.raw("/")
        self.assertEqual((status, headers["Location"]), (303, "/login"))
        self.assertEqual(self.raw("/", method="HEAD")[0], 303)
        status, _, page = self.raw("/login")
        self.assertEqual(status, 200)
        self.assertIn('id="register-form"', page.decode())
        self.assertEqual(self.raw("/health")[0], 200)
        task = {"title": "Prova", "subject": "Física", "due_date": "2026-12-01"}
        for path, method, data in [("/api/tasks", "GET", None), ("/api/tasks", "POST", task), ("/api/tasks/1", "PUT", task),
                                   ("/api/tasks/1", "DELETE", None), ("/api/tasks/export.csv", "GET", None), ("/api/me", "GET", None)]:
            with self.subTest(path=path, method=method):
                status, result = self.request(path, method, data)
                self.assertEqual(status, 401)
                self.assertEqual(result["error"], "Faça login para continuar.")
        self.assertEqual(self.raw("/api/tasks", cookie="agenda_sessao=token-inventado")[0], 401)

    def test_register_login_and_logout(self):
        status, headers, body = self.raw("/api/register", "POST", {**ANA, "username": "  Ana.Souza "})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["user"], {"name": "Ana Souza", "username": "ana.souza"})
        cookie_header = headers["Set-Cookie"]
        for flag in ("HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=604800"):
            self.assertIn(flag, cookie_header)
        self.cookie = cookie_header.split(";", 1)[0]
        self.assertEqual(self.request("/api/me"), (200, {"user": {"name": "Ana Souza", "username": "ana.souza"}}))
        self.assertEqual(self.raw("/login")[0], 303)  # já entrou: a tela de login manda para a agenda

        status, headers, _ = self.raw("/api/logout", "POST")
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("/api/me")[0], 401)  # a sessão antiga não vale mais

        self.assertEqual(self.request("/api/login", "POST", {"username": "ana.souza", "password": "errada123"}, cookie=""),
                         (401, {"error": "Usuário ou senha incorretos."}))
        self.assertEqual(self.request("/api/login", "POST", {"username": "nao.existe", "password": "senha-da-ana"}, cookie=""),
                         (401, {"error": "Usuário ou senha incorretos."}))
        status, headers, _ = self.raw("/api/login", "POST", {"username": "ANA.SOUZA", "password": "senha-da-ana"}, cookie="")
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("/api/me")[0], 200)

    def test_register_validation_and_duplicate_username(self):
        cases = {
            "nome": {**ANA, "name": "  "},
            "usuário": {**ANA, "username": "an"},
            "usuário com acento": {**ANA, "username": "joão"},
            "usuário com espaço": {**ANA, "username": "ana souza"},
            "senha curta": {**ANA, "password": "1234567"},
            "pergunta": {**ANA, "question": "?"},
            "resposta": {**ANA, "answer": " a "},
        }
        for label, account in cases.items():
            with self.subTest(label):
                status, result = self.request("/api/register", "POST", account)
                self.assertEqual(status, 400)
                self.assertIn("error", result)
        self.register()
        status, result = self.request("/api/register", "POST", {**ANA, "username": "ANA.souza", "name": "Outra Ana"}, cookie="")
        self.assertEqual((status, result["error"]), (409, "Este usuário já está em uso. Escolha outro."))

    def test_each_account_sees_only_its_own_tasks(self):
        ana = self.register()
        status, result = self.request("/api/tasks", "POST", {"title": "Tarefa da Ana", "subject": "História", "due_date": "2026-11-30"})
        ana_task = result["task"]
        bruno = self.register({**ANA, "name": "Bruno Lima", "username": "bruno"})
        self.assertEqual(self.request("/api/tasks")[1]["tasks"], [])
        # Bruno sabe o número da tarefa da Ana, mas não consegue alterá-la nem excluí-la.
        self.assertEqual(self.request(f"/api/tasks/{ana_task['id']}", "PUT", {**ana_task, "title": "Invadida"})[0], 404)
        self.assertEqual(self.request(f"/api/tasks/{ana_task['id']}", "DELETE")[0], 404)
        self.assertEqual(self.raw("/api/tasks/export.csv")[2].decode("utf-8-sig").splitlines()[1:], [])
        self.request("/api/tasks", "POST", {"title": "Tarefa do Bruno", "subject": "Física", "due_date": "2026-12-01"})
        self.assertEqual([t["title"] for t in self.request("/api/tasks", cookie=ana)[1]["tasks"]], ["Tarefa da Ana"])
        self.assertEqual([t["title"] for t in self.request("/api/tasks", cookie=bruno)[1]["tasks"]], ["Tarefa do Bruno"])

    def test_password_recovery_with_secret_question(self):
        old_session = self.register()
        self.assertEqual(self.request("/api/password/question", "POST", {"username": "Ana.Souza"}, cookie=""),
                         (200, {"question": "Qual o nome da minha primeira professora?"}))
        self.assertEqual(self.request("/api/password/question", "POST", {"username": "ninguem"}, cookie="")[0], 404)
        reset = {"username": "ana.souza", "answer": "Dona Maria", "new_password": "nova-senha-1"}
        self.assertEqual(self.request("/api/password/reset", "POST", reset, cookie=""), (401, {"error": "Resposta incorreta."}))
        self.assertEqual(self.request("/api/password/reset", "POST", {**reset, "new_password": "curta"}, cookie="")[0], 400)
        # Maiúsculas, acentos e espaços a mais não atrapalham a resposta certa.
        status, headers, _ = self.raw("/api/password/reset", "POST", {**reset, "answer": "  DONA   cecilia "}, cookie="")
        self.assertEqual(status, 200)
        self.assertEqual(self.request("/api/me", cookie=old_session)[0], 401)  # sai dos outros aparelhos
        self.assertEqual(self.request("/api/me", cookie=headers["Set-Cookie"].split(";", 1)[0])[0], 200)
        self.assertEqual(self.request("/api/login", "POST", {"username": "ana.souza", "password": "senha-da-ana"}, cookie="")[0], 401)
        self.assertEqual(self.request("/api/login", "POST", {"username": "ana.souza", "password": "nova-senha-1"}, cookie="")[0], 200)

    def test_too_many_wrong_attempts_are_blocked(self):
        self.register()
        wrong_login = {"username": "ana.souza", "password": "chute-errado"}
        for _ in range(5):
            self.assertEqual(self.request("/api/login", "POST", wrong_login, cookie="")[0], 401)
        status, result = self.request("/api/login", "POST", {**wrong_login, "password": "senha-da-ana"}, cookie="")
        self.assertEqual(status, 429)  # bloqueado mesmo com a senha certa, até passar o tempo
        self.assertIn("Aguarde 15 minutos", result["error"])
        wrong_answer = {"username": "ana.souza", "answer": "chute", "new_password": "outra-senha-1"}
        for _ in range(5):
            self.assertEqual(self.request("/api/password/reset", "POST", wrong_answer, cookie="")[0], 401)
        self.assertEqual(self.request("/api/password/reset", "POST", {**wrong_answer, "answer": "Dona Cecília"}, cookie="")[0], 429)

    def test_passwords_and_answers_are_not_stored_in_plain_text(self):
        self.register()
        with connect(self.db_path) as connection:
            user = connection.execute("SELECT * FROM users").fetchone()
            sessions = connection.execute("SELECT token_hash FROM sessions").fetchall()
        dump = json.dumps(dict(user), ensure_ascii=False)
        self.assertNotIn("senha-da-ana", dump)
        self.assertNotIn("Cecília", dump)
        self.assertTrue(user["password_hash"].startswith("pbkdf2_sha256$600000$"))
        self.assertNotEqual(user["password_hash"].split("$")[2], user["answer_hash"].split("$")[2], "cada hash tem o seu sal")
        self.assertNotIn(self.cookie.split("=", 1)[1], [row["token_hash"] for row in sessions])

    def test_project_plan_goes_to_the_first_account(self):
        self.assertEqual(seed_project_plan(self.db_path, date(2026, 11, 8)), 10)
        self.assertEqual(seed_project_plan(self.db_path, date(2026, 11, 8)), 0)
        self.register()
        tasks = self.request("/api/tasks")[1]["tasks"]
        self.assertEqual(len(tasks), 10)
        self.assertEqual(sum(task["completed"] for task in tasks), 4)
        self.assertTrue(any(task["title"] == "Revisar a documentação com a PIT I" for task in tasks))
        self.register({**ANA, "username": "segunda.conta"})
        self.assertEqual(self.request("/api/tasks")[1]["tasks"], [])  # contas novas começam vazias

    def test_hosting_account_is_created_and_keeps_password_in_sync(self):
        seed_project_plan(self.db_path, date(2026, 11, 8))
        ensure_account(self.db_path, "avaliador", "Senha-Do-Painel1")
        ensure_account(self.db_path, "avaliador", "Senha-Trocada-2")  # reinício com outra senha no painel
        self.assertEqual(self.request("/api/login", "POST", {"username": "avaliador", "password": "Senha-Do-Painel1"})[0], 401)
        status, headers, _ = self.raw("/api/login", "POST", {"username": "avaliador", "password": "Senha-Trocada-2"})
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(len(self.request("/api/tasks")[1]["tasks"]), 10)
        # A conta da hospedagem não tem pergunta secreta: a senha não pode ser trocada pela tela.
        self.assertEqual(self.request("/api/password/question", "POST", {"username": "avaliador"})[0], 400)


class MigrationTests(unittest.TestCase):
    def test_database_from_version_1_receives_new_columns(self):
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
            initialize(db_path)  # rodar de novo não deve dar erro nem duplicar colunas

            with connect(db_path) as connection:
                columns = [row["name"] for row in connection.execute("PRAGMA table_info(tasks)")]
                row = connection.execute("SELECT title, priority, due_time, user_id FROM tasks").fetchone()
            for column in ("priority", "due_time", "user_id"):
                self.assertEqual(columns.count(column), 1)
            self.assertEqual(tuple(row), ("Tarefa antiga", "media", "", None))

    def test_database_from_version_2_2_keeps_tasks_for_the_first_account(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "agenda.db"
            # Estrutura da versão 2.2: prioridade e horário, mas ainda sem contas.
            connection = sqlite3.connect(db_path)
            connection.executescript("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, subject TEXT NOT NULL,
                    due_date TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
                    priority TEXT NOT NULL DEFAULT 'media' CHECK (priority IN ('baixa', 'media', 'alta')),
                    due_time TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                INSERT INTO tasks (title, subject, due_date, notes, completed, priority, due_time, created_at, updated_at)
                VALUES ('Tarefa da 2.2', 'Física', '2026-11-20', '', 0, 'alta', '14:00', 'x', 'x');
            """)
            connection.close()

            initialize(db_path)
            user_id = ensure_account(db_path, "avaliador", "Senha-Do-Painel1")
            with connect(db_path) as connection:
                row = connection.execute("SELECT title, priority, due_time, user_id FROM tasks").fetchone()
            self.assertEqual(tuple(row), ("Tarefa da 2.2", "alta", "14:00", user_id))


class ServerStartTests(unittest.TestCase):
    def start(self, env_changes, remove=()):
        app_dir = Path(__file__).resolve().parent.parent
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        env = {**os.environ, "PORT": "0", "AGENDA_DB_PATH": str(Path(tempdir.name) / "agenda.db"), **env_changes}
        for name in remove:
            env.pop(name, None)
        process = subprocess.Popen([sys.executable, "app.py"], cwd=app_dir, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)

        def stop():
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()

        self.addCleanup(stop)
        return process

    def test_hosting_log_shows_public_address(self):
        process = self.start({"HOST": "0.0.0.0", "RENDER_EXTERNAL_URL": "https://exemplo.onrender.com"}, remove=("AGENDA_SENHA",))
        lines = [process.stdout.readline().strip() for _ in range(2)]
        self.assertEqual(lines[0], "Agenda Acadêmica 2.3 publicada em https://exemplo.onrender.com")
        self.assertIn("AGENDA_SENHA não definida", lines[1])

    def test_hosting_account_password_ignores_spaces_and_quotes(self):
        process = self.start({"HOST": "127.0.0.1", "AGENDA_SENHA": '  "Senha-Teste9"\n'},
                             remove=("RENDER_EXTERNAL_URL", "AGENDA_USUARIO"))
        first, second = process.stdout.readline().strip(), process.stdout.readline().strip()
        base = first.split(": ", 1)[1]
        self.assertEqual(second, "Conta de acesso pronta (usuário: avaliador; senha com 12 caracteres).")

        def login(password):
            request = Request(base + "/api/login", data=json.dumps({"username": "avaliador", "password": password}).encode(),
                              method="POST", headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=5) as response:
                    return response.status
            except HTTPError as error:
                with error:
                    return error.code

        self.assertEqual(login('"Senha-Teste9"'), 401)
        self.assertEqual(login("Senha-Teste9"), 200)

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
