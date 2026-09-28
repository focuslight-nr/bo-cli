import json
from types import SimpleNamespace
import pytest
from aiohttp import web
import gui_server


@pytest.fixture(autouse=True)
def gui_config_path(tmp_path, monkeypatch):
    p = tmp_path / "gui.json"
    monkeypatch.setattr(gui_server, "GUI_CONFIG_PATH", p)
    return p


@pytest.fixture
def music_dir(tmp_path, monkeypatch):
    root = tmp_path / "music"
    (root / "album").mkdir(parents=True)
    (root / "album" / "song.flac").write_bytes(b"x")
    monkeypatch.setattr(gui_server, "music_root", lambda: root)
    return root


def test_load_gui_config_missing_returns_default(gui_config_path):
    result = gui_server.load_gui_config()
    assert result == gui_server.DEFAULT_GUI_CONFIG


def test_load_gui_config_missing_is_deep_copy(gui_config_path):
    result = gui_server.load_gui_config()
    original_val = gui_server.DEFAULT_GUI_CONFIG["night"]["maxVolume"]
    result["night"]["maxVolume"] = 999
    assert gui_server.DEFAULT_GUI_CONFIG["night"]["maxVolume"] == original_val


def test_load_gui_config_partial_night_merges_defaults(gui_config_path):
    data = {"night": {"maxVolume": 20}}
    gui_config_path.write_text(json.dumps(data))
    result = gui_server.load_gui_config()
    assert result["night"]["maxVolume"] == 20
    assert result["night"]["start"] == "22:00"
    assert result["night"]["enabled"] is False


def test_load_gui_config_ignores_unknown_keys(gui_config_path):
    data = {"bogus": 1}
    gui_config_path.write_text(json.dumps(data))
    result = gui_server.load_gui_config()
    assert "bogus" not in result


def test_load_gui_config_music_dir_override(gui_config_path):
    data = {"musicDir": "/custom/music"}
    gui_config_path.write_text(json.dumps(data))
    result = gui_server.load_gui_config()
    assert result["musicDir"] == "/custom/music"


def test_load_gui_config_music_dir_default(gui_config_path):
    data = {}
    gui_config_path.write_text(json.dumps(data))
    result = gui_server.load_gui_config()
    assert result["musicDir"] == "~/Music"


def test_pick_art_url_meta_none():
    assert gui_server.pick_art_url(None, "10.0.0.5") is None


def test_pick_art_url_empty_art_list():
    meta = SimpleNamespace(art=[])
    assert gui_server.pick_art_url(meta, "10.0.0.5") is None


def test_pick_art_url_relative_url_prefixes_host():
    art_item = SimpleNamespace(key="640x640", url="/api/v1/art.jpg")
    meta = SimpleNamespace(art=[art_item])
    result = gui_server.pick_art_url(meta, "10.0.0.5")
    assert result == "http://10.0.0.5/api/v1/art.jpg"


def test_pick_art_url_absolute_url_unchanged():
    art_item = SimpleNamespace(key="640x640", url="https://cdn.example/a.jpg")
    meta = SimpleNamespace(art=[art_item])
    result = gui_server.pick_art_url(meta, "10.0.0.5")
    assert result == "https://cdn.example/a.jpg"


def test_pick_art_url_empty_url_returns_none():
    art_item = SimpleNamespace(key="640x640", url="")
    meta = SimpleNamespace(art=[art_item])
    assert gui_server.pick_art_url(meta, "10.0.0.5") is None


def test_pick_art_url_picks_largest():
    items = [
        SimpleNamespace(key="160x160", url="/small.jpg"),
        SimpleNamespace(key="640x640", url="/large.jpg"),
        SimpleNamespace(key="320x320", url="/medium.jpg"),
    ]
    meta = SimpleNamespace(art=items)
    result = gui_server.pick_art_url(meta, "10.0.0.5")
    assert result == "http://10.0.0.5/large.jpg"


def test_pick_art_url_malformed_key_treated_as_zero():
    items = [
        SimpleNamespace(key="bogus", url="/bad.jpg"),
        SimpleNamespace(key="300x300", url="/good.jpg"),
    ]
    meta = SimpleNamespace(art=items)
    result = gui_server.pick_art_url(meta, "10.0.0.5")
    assert result == "http://10.0.0.5/good.jpg"


def test_pick_art_url_none_key_treated_as_zero():
    items = [
        SimpleNamespace(key=None, url="/none.jpg"),
        SimpleNamespace(key="300x300", url="/good.jpg"),
    ]
    meta = SimpleNamespace(art=items)
    result = gui_server.pick_art_url(meta, "10.0.0.5")
    assert result == "http://10.0.0.5/good.jpg"


def test_resolve_media_path_valid_relative(music_dir):
    p = gui_server.resolve_media_path("album/song.flac")
    assert p.exists()
    assert str(p).endswith("album/song.flac")


def test_resolve_media_path_empty_returns_root(music_dir):
    p = gui_server.resolve_media_path("")
    assert p == music_dir.resolve()


def test_resolve_media_path_traversal_dotdot_raises(music_dir):
    with pytest.raises(web.HTTPForbidden):
        gui_server.resolve_media_path("../secret.txt")


def test_resolve_media_path_traversal_deep_raises(music_dir):
    with pytest.raises(web.HTTPForbidden):
        gui_server.resolve_media_path("album/../../etc/passwd")


def test_resolve_media_path_absolute_raises(music_dir):
    with pytest.raises(web.HTTPForbidden):
        gui_server.resolve_media_path("/etc/passwd")
