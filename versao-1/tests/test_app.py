"""Testes de integração da API usando um banco de dados temporário."""

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import handler_factory, initialize, seed_project_plan


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
        task = {"title": "Estudar matemática", "subject": "Matemática", "due_date": "2026-11-20", "notes": "Capítulo 3", "completed": False}
        status, result = self.request("/api/tasks", "POST", task)
        self.assertEqual(status, 201)
        task_id = result["task"]["id"]
        self.assertFalse(result["task"]["completed"])

        status, result = self.request("/api/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["title"], task["title"])

        updated = {**task, "title": "Revisar matemática", "completed": True}
        status, result = self.request(f"/api/tasks/{task_id}", "PUT", updated)
        self.assertEqual(status, 200)
        self.assertEqual(result["task"]["title"], updated["title"])
        self.assertTrue(result["task"]["completed"])

        status, result = self.request(f"/api/tasks/{task_id}", "PUT", {**updated, "completed": False})
        self.assertEqual(status, 200)
        self.assertFalse(result["task"]["completed"])

        # Abre o mesmo banco em outra conexão para verificar a gravação real.
        from app import connect
        with connect(self.db_path) as connection:
            saved = connection.execute("SELECT title, completed FROM tasks WHERE id=?", (task_id,)).fetchone()
        self.assertEqual((saved["title"], saved["completed"]), ("Revisar matemática", 0))

        status, result = self.request(f"/api/tasks/{task_id}", "DELETE")
        self.assertEqual((status, result), (200, {"deleted": True}))
        self.assertEqual(self.request("/api/tasks")[1]["tasks"], [])

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
            self.assertIn("Agenda Acadêmica", response.read().decode())
        for path, expected in [("/styles.css", "text/css"), ("/app.js", "text/javascript")]:
            with urlopen(self.base + path, timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(expected, response.headers["Content-Type"])
                self.assertGreater(len(response.read()), 100)
        self.assertEqual(self.request("/health"), (200, {"status": "ok"}))
        self.assertEqual(self.request("/api/unknown")[0], 404)

    def test_project_plan_only_populates_an_empty_database(self):
        from datetime import date
        self.assertEqual(seed_project_plan(self.db_path, date(2026, 11, 8)), 10)
        self.assertEqual(seed_project_plan(self.db_path, date(2026, 11, 8)), 0)
        tasks = self.request("/api/tasks")[1]["tasks"]
        self.assertEqual(len(tasks), 10)
        self.assertEqual(sum(task["completed"] for task in tasks), 4)
        self.assertTrue(any(task["title"] == "Revisar a documentação com a PIT I" for task in tasks))
        self.assertTrue(all(len(task["notes"]) > 40 for task in tasks))


if __name__ == "__main__":
    unittest.main()
