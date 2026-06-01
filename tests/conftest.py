from __future__ import annotations

import sys
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "web-dashboard" / "backend"

for path in (PROJECT_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    import database_utils
    import data_access
    import time_override

    db_path = tmp_path / "face_records.db"
    log_path = tmp_path / "attendance_logs.txt"
    override_path = tmp_path / ".test_time_override.json"

    monkeypatch.setattr(database_utils, "DB_PATH", db_path)
    monkeypatch.setattr(database_utils, "LOG_PATH", log_path)
    monkeypatch.setattr(database_utils, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(data_access, "DB_PATH", db_path)
    monkeypatch.setattr(data_access, "LOG_PATH", log_path)
    monkeypatch.setattr(time_override, "OVERRIDE_PATH", override_path)

    return {"db": db_path, "log": log_path, "override": override_path, "root": tmp_path}


@pytest.fixture
def fixed_now(monkeypatch):
    import database_utils
    import data_access

    now = datetime(2026, 5, 30, 9, 20, 0)
    monkeypatch.setattr(database_utils, "get_current_datetime", lambda: now)
    monkeypatch.setattr(data_access, "get_current_datetime", lambda: now)
    return now


@pytest.fixture
def initialized_db(isolated_paths):
    import database_utils

    database_utils.init_db()
    return isolated_paths


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@pytest.fixture
def dashboard_app(initialized_db, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret1")

    import app

    monkeypatch.setattr(app, "PROJECT_SOURCE_DIR", initialized_db["root"])
    app.seed_env_admin()
    return app


@pytest.fixture
def dashboard_server(dashboard_app):
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_app.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class Client:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        def request(self, method, path, body=None, cookie=None, follow_redirects=True):
            data = None
            headers = {}
            if body is not None:
                import json

                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            if cookie:
                headers["Cookie"] = cookie

            opener = build_opener() if follow_redirects else build_opener(NoRedirectHandler)
            request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
            try:
                response = opener.open(request, timeout=5)
                return response.status, dict(response.headers), response.read()
            except HTTPError as exc:
                return exc.code, dict(exc.headers), exc.read()

    try:
        yield Client()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
