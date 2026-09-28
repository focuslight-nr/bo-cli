"""make_client が既定のリクエストタイムアウトを入れることの検証。

mozart-api の既定は1リクエスト5分。スピーカーがディープスタンバイで
応答しないとき、これが効かないとCLIもGUIも固まったままになる。
"""

import time

import pytest
from mozart_api.rest import RESTClientObject

import bo

BLACKHOLE = "192.0.2.1"  # RFC 5737 TEST-NET-1。到達しないことが保証されている


@pytest.fixture
def recorded(monkeypatch) -> list:
    """REST層のrequest()を記録用スタブに差し替える。"""
    calls = []

    async def fake_request(self, *args, _request_timeout=None, **kwargs):
        calls.append(_request_timeout)
        return None

    monkeypatch.setattr(RESTClientObject, "request", fake_request)
    return calls


async def test_default_timeout_is_injected(recorded):
    client = bo.make_client(BLACKHOLE)
    await client.api_client.rest_client.request("GET", "http://x/")
    assert recorded == [bo.REQUEST_TIMEOUT]


async def test_explicit_timeout_is_preserved(recorded):
    client = bo.make_client(BLACKHOLE)
    await client.api_client.rest_client.request("GET", "http://x/", _request_timeout=2)
    assert recorded == [2]


def test_default_timeout_is_shorter_than_the_library_default():
    # mozart-api 側の既定は 5*60 秒
    assert 0 < bo.REQUEST_TIMEOUT < 300


async def test_unreachable_host_gives_up_within_the_timeout(monkeypatch):
    """応答しないホストに対してタイムアウトで打ち切る(5分待たない)。"""
    monkeypatch.setattr(bo, "REQUEST_TIMEOUT", 1.0)
    client = bo.make_client(BLACKHOLE)
    started = time.monotonic()
    try:
        with pytest.raises(Exception):
            await client.get_current_volume()
    finally:
        await client.close_api_client()
    assert time.monotonic() - started < 10
