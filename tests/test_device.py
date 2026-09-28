"""実機に対する読み取り専用の疎通テスト。

`--device` を付けたときだけ実行される。スピーカーの状態は一切変更しない
(音量・再生・スタンバイに触れない)。
"""

import pytest

import bo

pytestmark = pytest.mark.device


@pytest.fixture(scope="module")
def host() -> str:
    config = bo.load_config()
    if not config["devices"]:
        pytest.skip("デバイス未登録。`bo discover` を先に実行してください")
    return bo.resolve_host(None)


async def test_default_device_is_reachable(host):
    from mozart_api.mozart_client import MozartClient

    client = MozartClient(host)
    try:
        volume = await client.get_current_volume()
    finally:
        await client.close_api_client()
    assert volume.level is not None
    assert 0 <= volume.level.level <= 100


async def test_playback_state_is_readable(host):
    from mozart_api.mozart_client import MozartClient

    client = MozartClient(host)
    try:
        playback = await client.get_playback_state()
    finally:
        await client.close_api_client()
    # スタンバイ中は state が None のこともあるので存在のみ確認する
    assert hasattr(playback, "state")


async def test_do_status_prints_against_real_device(host, capsys):
    from mozart_api.mozart_client import MozartClient

    client = MozartClient(host)
    try:
        await bo.do_status(client)
    finally:
        await client.close_api_client()
    out = capsys.readouterr().out
    assert "再生状態:" in out
