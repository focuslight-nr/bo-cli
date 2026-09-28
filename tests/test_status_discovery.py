from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import bo

def make_client(volume, playback):
    client = AsyncMock()
    client.get_current_volume.return_value = volume
    client.get_playback_state.return_value = playback
    return client

def make_volume(level=30, muted=False):
    return SimpleNamespace(level=SimpleNamespace(level=level),
                           muted=SimpleNamespace(muted=muted))

def make_playback(state="playing", source="spotify", title="Song", artist="Artist"):
    return SimpleNamespace(
        state=SimpleNamespace(value=state) if state is not None else None,
        source=SimpleNamespace(type=SimpleNamespace(value=source)) if source is not None else None,
        metadata=SimpleNamespace(title=title, artist_name=artist) if (title or artist) else None,
    )

def make_info(addresses=(b"\xc0\xa8\x01\x0a",), props=None):
    return SimpleNamespace(addresses=list(addresses),
                           properties=dict(props or {}))

class FakeZc:
    def __init__(self, info):
        self.info = info
    def get_service_info(self, type_, name):
        return self.info

async def test_full_data(capsys):
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state="playing", source="spotify", title="Song", artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert "再生状態: playing" in out
    assert "ソース: spotify" in out
    assert "曲: Artist / Song" in out
    assert "音量: 30" in out
    assert "ミュート中" not in out

async def test_muted(capsys):
    vol = make_volume(level=30, muted=True)
    pb = make_playback(state="playing", source="spotify", title="Song", artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert "(ミュート中)" in out

async def test_state_none(capsys):
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state=None, source="spotify", title="Song", artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert "再生状態: ?" in out

async def test_source_none(capsys):
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state="playing", source=None, title="Song", artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert not any(line.startswith("ソース:") for line in out.splitlines())

async def test_metadata_none(capsys):
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state="playing", source="spotify", title=None, artist=None)
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert not any(line.startswith("曲:") for line in out.splitlines())

async def test_metadata_artist_only(capsys):
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state="playing", source="spotify", title=None, artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert "曲: Artist" in out

async def test_metadata_title_only(capsys):
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state="playing", source="spotify", title="Song", artist=None)
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert "曲: Song" in out

async def test_volume_level_none(capsys):
    vol = SimpleNamespace(level=None, muted=SimpleNamespace(muted=False))
    pb = make_playback(state="playing", source="spotify", title="Song", artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    out = capsys.readouterr().out
    assert not any(line.startswith("音量:") for line in out.splitlines())

async def test_do_status_awaits_methods():
    vol = make_volume(level=30, muted=False)
    pb = make_playback(state="playing", source="spotify", title="Song", artist="Artist")
    client = make_client(vol, pb)
    await bo.do_status(client)
    client.get_current_volume.assert_awaited_once()
    client.get_playback_state.assert_awaited_once()

def test_add_service_info_none():
    listener = bo._Listener()
    zc = FakeZc(None)
    listener.add_service(zc, "type", "name")
    assert listener.found == {}

def test_add_service_empty_addresses():
    listener = bo._Listener()
    info = make_info(addresses=[])
    zc = FakeZc(info)
    listener.add_service(zc, "type", "name")
    assert listener.found == {}

def test_add_service_full_props():
    listener = bo._Listener()
    props = {b"fn": b"Living Room", b"pm": b"Beosound Emerge", b"sn": b"12345"}
    info = make_info(props=props)
    zc = FakeZc(info)
    listener.add_service(zc, "type", "name")
    assert listener.found["Living Room"] == {
        "ip": "192.168.1.10",
        "model": "Beosound Emerge",
        "serial": "12345"
    }

def test_add_service_fallback_name():
    listener = bo._Listener()
    props = {b"pm": b"Model", b"sn": b"SN"}
    info = make_info(props=props)
    zc = FakeZc(info)
    listener.add_service(zc, "type", "Speaker._bangolufsen._tcp.local.")
    assert "Speaker" in listener.found

def test_add_service_missing_pm_sn():
    listener = bo._Listener()
    props = {b"fn": b"Room"}
    info = make_info(props=props)
    zc = FakeZc(info)
    listener.add_service(zc, "type", "name")
    assert listener.found["Room"]["model"] == "?"
    assert listener.found["Room"]["serial"] == "?"

def test_add_service_str_prop():
    listener = bo._Listener()
    props = {b"fn": "Kitchen"}
    info = make_info(props=props)
    zc = FakeZc(info)
    listener.add_service(zc, "type", "name")
    assert "Kitchen" in listener.found
