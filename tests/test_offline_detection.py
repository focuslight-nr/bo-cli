"""スピーカー到達不能(スタンバイ等)の検出とAPIラッパーのoffline応答。"""

import asyncio

import pytest
from aiohttp import ClientConnectorError, web
from aiohttp.test_utils import make_mocked_request

import gui_server


@pytest.mark.parametrize(
    "exc",
    [
        OSError("[Errno 65] No route to host"),
        asyncio.TimeoutError(),
        Exception("Cannot connect to host 192.168.26.179:80"),
        Exception("Other: No route to host while connecting"),
    ],
)
def test_offline_errors_detected(exc):
    assert gui_server.is_offline_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("bad json"),
        KeyError("missing"),
        Exception("400 Bad Request"),
    ],
)
def test_non_offline_errors_not_flagged(exc):
    assert gui_server.is_offline_error(exc) is False


def test_client_connector_error_is_offline():
    # aiohttp の接続失敗は常に offline 扱い
    conn_key = type("K", (), {"host": "h", "port": 80, "ssl": None, "is_ssl": lambda self: False})()
    err = ClientConnectorError(conn_key, OSError("No route to host"))
    assert gui_server.is_offline_error(err) is True


def _run(coro):
    return asyncio.run(coro)


def test_api_wrapper_returns_503_offline(monkeypatch):
    async def boom(request, client):
        raise OSError("[Errno 65] No route to host")

    class DummyClient:
        async def close_api_client(self):
            pass

    monkeypatch.setattr(gui_server, "client_for", lambda request: DummyClient())
    handler = _run(gui_server.api(boom))
    req = make_mocked_request("GET", "/api/state")
    resp = _run(handler(req))
    assert resp.status == 503
    import json

    body = json.loads(resp.body)
    assert body["offline"] is True


def test_api_wrapper_returns_502_for_other_errors(monkeypatch):
    async def boom(request, client):
        raise ValueError("bad request")

    class DummyClient:
        async def close_api_client(self):
            pass

    monkeypatch.setattr(gui_server, "client_for", lambda request: DummyClient())
    handler = _run(gui_server.api(boom))
    req = make_mocked_request("GET", "/api/state")
    resp = _run(handler(req))
    assert resp.status == 502
    import json

    body = json.loads(resp.body)
    assert "offline" not in body
