from __future__ import annotations

import base64
import json
from datetime import datetime

import numpy as np


def test_session_tokens_accept_valid_and_reject_tampered_or_expired(dashboard_app, monkeypatch):
    monkeypatch.setattr(dashboard_app.time, "time", lambda: 1000)

    token = dashboard_app.encode_session_token("admin")
    assert dashboard_app.decode_session_token(token) == {"username": "admin"}

    token_part, signature = token.rsplit(".", 1)
    tampered = f"{token_part[:-1]}x.{signature}"
    assert dashboard_app.decode_session_token(tampered) is None

    monkeypatch.setattr(dashboard_app.time, "time", lambda: 1000 + dashboard_app.SESSION_DURATION_SECONDS + 1)
    assert dashboard_app.decode_session_token(token) is None


def test_duplicate_name_and_face_registration_checks(initialized_db, dashboard_app, monkeypatch):
    import database_utils

    database_utils.insert_user("Ada Lovelace", json.dumps([0.1, 0.2]))
    assert database_utils.employee_name_exists("ada lovelace") == "Ada Lovelace"

    frame = np.zeros((32, 32, 3), dtype=np.uint8)

    class FakeCv2:
        IMREAD_COLOR = 1
        COLOR_BGR2RGB = 2

        @staticmethod
        def imdecode(image_array, mode):
            return frame

        @staticmethod
        def cvtColor(image, mode):
            return image

        @staticmethod
        def imwrite(path, image):
            return True

    class FakeFaceRecognition:
        @staticmethod
        def face_locations(image):
            return [(4, 16, 16, 4)]

        @staticmethod
        def face_encodings(image, locations):
            return [np.array([0.12, 0.22])]

        @staticmethod
        def face_distance(known_encodings, face_encoding):
            return np.array([0.42])

    monkeypatch.setattr(dashboard_app, "cv2", FakeCv2)
    monkeypatch.setattr(dashboard_app, "face_recognition", FakeFaceRecognition)

    cookie = dashboard_app.build_session_cookie("admin").split(";", 1)[0]
    image = "data:image/jpeg;base64," + base64.b64encode(b"fake").decode("ascii")
    status, _, body = _dashboard_request(
        dashboard_app,
        "POST",
        "/api/employees/register",
        {"name": "Different Person", "image": image},
        cookie=cookie,
    )

    assert status == 409
    assert "Ada Lovelace" in body.decode("utf-8")


def _dashboard_request(app_module, method, path, body=None, cookie=None):
    from http.server import ThreadingHTTPServer
    import threading
    from urllib.error import HTTPError
    from urllib.request import Request, build_opener

    server = ThreadingHTTPServer(("127.0.0.1", 0), app_module.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        request = Request(
            f"http://127.0.0.1:{server.server_address[1]}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            response = build_opener().open(request, timeout=5)
            return response.status, dict(response.headers), response.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
