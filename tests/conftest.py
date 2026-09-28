"""GUIサーバーのHTTPテスト用フィクスチャ。

実機にもユーザーの設定ファイルにも触れないよう、
GUI_CONFIG_PATH / bo.CONFIG_PATH / music_root / client_for を差し替える。
"""

import json
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import bo
import gui_server


@pytest.fixture
def gui_config(tmp_path, monkeypatch):
    """GUI設定ファイルを一時パスへ逃がす。書き込み済みの内容を読み書きできる。"""
    path = tmp_path / "gui.json"
    monkeypatch.setattr(gui_server, "GUI_CONFIG_PATH", path)
    return path


@pytest.fixture
def device_config(tmp_path, monkeypatch):
    """bo 側のデバイス一覧を一時パスへ逃がし、1台登録済みにする。"""
    path = tmp_path / "devices.json"
    path.write_text(
        json.dumps(
            {
                "default": "リビング",
                "devices": {"リビング": {"ip": "192.168.1.10", "model": "Emerge", "serial": "1"}},
            }
        )
    )
    monkeypatch.setattr(bo, "CONFIG_PATH", path)
    return path


@pytest.fixture
def music_dir(tmp_path, monkeypatch):
    """音楽フォルダを一時ディレクトリに差し替える。"""
    root = tmp_path / "music"
    (root / "album").mkdir(parents=True)
    (root / "album" / "song.flac").write_bytes(b"FLACDATA")
    monkeypatch.setattr(gui_server, "music_root", lambda: root)
    return root


@pytest.fixture
def mock_client(monkeypatch):
    """api() ラッパーが掴む MozartClient を AsyncMock に差し替える。"""
    client = AsyncMock()
    monkeypatch.setattr(gui_server, "client_for", lambda request: client)
    return client


async def _build_app() -> web.Application:
    """テスト対象のルートだけを登録したアプリ。

    make_app() と違い cleanup_ctx を張らないので、
    夜間スケジューラも実機への WebSocket 接続も起動しない。
    """
    app = web.Application()
    r = app.router
    r.add_get("/api/devices", gui_server.h_devices)
    r.add_get("/api/night", gui_server.h_night_get)
    r.add_put("/api/night", gui_server.h_night_put)
    r.add_get("/api/tts-volume", gui_server.h_tts_volume_get)
    r.add_put("/api/tts-volume", gui_server.h_tts_volume_put)
    r.add_get("/api/music-dir", gui_server.h_music_dir_get)
    r.add_put("/api/music-dir", gui_server.h_music_dir_put)
    r.add_get("/api/favorites", gui_server.h_favorites_get)
    r.add_put("/api/favorites", gui_server.h_favorites_put)
    r.add_get("/api/library", gui_server.h_library)
    r.add_get("/media/{path:.*}", gui_server.h_media)
    r.add_get("/api/state", await gui_server.api(gui_server.h_state))
    r.add_get("/api/queue-settings", await gui_server.api(gui_server.h_queue_settings_get))
    r.add_post("/api/queue-settings", await gui_server.api(gui_server.h_queue_settings_post))
    r.add_get("/api/volume-settings", await gui_server.api(gui_server.h_volume_settings_get))
    r.add_post("/api/volume-settings", await gui_server.api(gui_server.h_volume_settings_post))
    r.add_post("/api/adjustments", await gui_server.api(gui_server.h_adjustments))
    r.add_post("/api/volume", await gui_server.api(gui_server.h_volume))
    r.add_post("/api/say", await gui_server.api(gui_server.h_say))
    r.add_post("/api/favorites/play", await gui_server.api(gui_server.h_favorite_play))
    return app


@pytest.fixture
async def cli(gui_config, device_config, mock_client):
    """テスト用HTTPクライアント。ポートは自動割り当て。"""
    client = TestClient(TestServer(await _build_app()))
    await client.start_server()
    yield client
    await client.close()
