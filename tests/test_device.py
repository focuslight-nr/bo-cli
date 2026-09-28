"""実機に対する読み取り専用の疎通テスト。

`--device` を付けたときだけ実行される。スピーカーの状態は一切変更しない
(音量・再生・スタンバイに触れない)。

B&Oのスピーカーはディープスタンバイ中にネットワークインターフェースごと
眠ることがあり、その間は接続できない。眠っているだけなら失敗ではないので
skip に落とす(実機が応答しているのに壊れている場合だけ fail させたい)。
"""

import contextlib
import socket

import pytest
from aiohttp import ClientError

import bo

pytestmark = pytest.mark.device

# 接続できない = 眠っている、とみなす例外
UNREACHABLE = (ClientError, OSError, TimeoutError)


@pytest.fixture(scope="module")
def host() -> str:
    config = bo.load_config()
    if not config["devices"]:
        pytest.skip("デバイス未登録。`bo discover` を先に実行してください")
    ip = bo.resolve_host(None)
    # 本テストに入る前に一度だけ疎通を確認する(眠っていれば以降まとめてskip)
    with socket.socket() as s:
        s.settimeout(3)
        try:
            s.connect((ip, 80))
        except OSError as e:
            pytest.skip(f"スピーカー {ip} に接続できない(スタンバイ中?): {e}")
    return ip


@contextlib.asynccontextmanager
async def device(host: str):
    """MozartClientを開閉する。接続不能なら fail ではなく skip。"""
    client = bo.make_client(host)
    try:
        yield client
    except UNREACHABLE as e:
        pytest.skip(f"スピーカーとの通信が切れた(スタンバイ中?): {e}")
    finally:
        await client.close_api_client()


async def test_default_device_is_reachable(host):
    async with device(host) as client:
        volume = await client.get_current_volume()
    assert volume.level is not None
    assert 0 <= volume.level.level <= 100


async def test_playback_state_is_readable(host):
    async with device(host) as client:
        playback = await client.get_playback_state()
    # スタンバイ中は state が None のこともあるので存在のみ確認する
    assert hasattr(playback, "state")


async def test_do_status_prints_against_real_device(host, capsys):
    async with device(host) as client:
        await bo.do_status(client)
    out = capsys.readouterr().out
    assert "再生状態:" in out
