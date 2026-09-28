from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import gui_server


@pytest.fixture
def started(monkeypatch):
    """start_local_file を記録用スタブに差し替え、渡された次のファイル名を集める。"""
    calls = []

    async def fake_start(client, rel, device_ip):
        calls.append(rel)

    monkeypatch.setattr(gui_server, "start_local_file", fake_start)
    monkeypatch.setattr(gui_server, "resolve_host", lambda _: "192.168.1.10")
    return calls


@pytest.fixture
def player(monkeypatch):
    """再生中ファイルとフォルダ一覧、キュー設定を組み立てるヘルパーを返す。"""

    def setup(path, folder, repeat="none", shuffle=False, client=True, raises=False):
        monkeypatch.setitem(gui_server.local_play, "path", path)
        monkeypatch.setitem(gui_server.local_play, "folder", folder)
        mozart = None
        if client:
            mozart = AsyncMock()
            if raises:
                mozart.get_settings_queue.side_effect = RuntimeError("boom")
            else:
                mozart.get_settings_queue.return_value = SimpleNamespace(
                    repeat=repeat, shuffle=shuffle
                )
        monkeypatch.setattr(gui_server.live, "mozart", mozart)
        return mozart

    return setup


# 進まない条件（start_local_file が1度も呼ばれない）

async def test_path_is_none(started, player):
    player(path=None, folder=["a.flac", "b.flac", "c.flac"])
    await gui_server.play_next_in_folder()
    assert started == []


async def test_path_not_in_folder(started, player):
    player(path="gone.flac", folder=["a.flac", "b.flac", "c.flac"])
    await gui_server.play_next_in_folder()
    assert started == []


async def test_client_is_none(started, player):
    player(path="a.flac", folder=["a.flac", "b.flac", "c.flac"], client=False)
    await gui_server.play_next_in_folder()
    assert started == []


async def test_empty_folder(started, player):
    player(path="a.flac", folder=[])
    await gui_server.play_next_in_folder()
    assert started == []


# 通常送り（repeat "none", shuffle False）

async def test_normal_advance_first_file(started, player):
    player(path="a.flac", folder=["a.flac", "b.flac", "c.flac"])
    await gui_server.play_next_in_folder()
    assert started == ["b.flac"]


async def test_normal_advance_middle_file(started, player):
    player(path="b.flac", folder=["a.flac", "b.flac", "c.flac"])
    await gui_server.play_next_in_folder()
    assert started == ["c.flac"]


async def test_normal_advance_last_file_stops(started, player):
    player(path="c.flac", folder=["a.flac", "b.flac", "c.flac"])
    await gui_server.play_next_in_folder()
    assert started == []


# repeat "all"

async def test_repeat_all_wraps_around(started, player):
    player(path="c.flac", folder=["a.flac", "b.flac", "c.flac"], repeat="all")
    await gui_server.play_next_in_folder()
    assert started == ["a.flac"]


async def test_repeat_all_mid_folder_unaffected(started, player):
    player(path="a.flac", folder=["a.flac", "b.flac", "c.flac"], repeat="all")
    await gui_server.play_next_in_folder()
    assert started == ["b.flac"]


# repeat "track"

async def test_repeat_track_same_file(started, player):
    player(path="b.flac", folder=["a.flac", "b.flac", "c.flac"], repeat="track")
    await gui_server.play_next_in_folder()
    assert started == ["b.flac"]


async def test_repeat_track_last_file(started, player):
    player(path="c.flac", folder=["a.flac", "b.flac", "c.flac"], repeat="track")
    await gui_server.play_next_in_folder()
    assert started == ["c.flac"]


# shuffle

async def test_shuffle_picks_other_file(started, player):
    player(path="a.flac", folder=["a.flac", "b.flac", "c.flac"], shuffle=True)
    await gui_server.play_next_in_folder()
    assert len(started) == 1 and started[0] != "a.flac"


async def test_shuffle_single_file_fallback(started, player):
    player(path="a.flac", folder=["a.flac"], shuffle=True)
    await gui_server.play_next_in_folder()
    assert started == ["a.flac"]


async def test_repeat_track_beats_shuffle(started, player):
    player(path="b.flac", folder=["a.flac", "b.flac", "c.flac"], repeat="track", shuffle=True)
    await gui_server.play_next_in_folder()
    assert started == ["b.flac"]


async def test_shuffle_last_file_ignores_end(started, player):
    player(path="c.flac", folder=["a.flac", "b.flac", "c.flac"], shuffle=True)
    await gui_server.play_next_in_folder()
    assert len(started) == 1 and started[0] != "c.flac"


# キュー設定の取得に失敗したとき

async def test_settings_queue_raises_fallback_normal(started, player):
    player(path="a.flac", folder=["a.flac", "b.flac", "c.flac"], raises=True)
    await gui_server.play_next_in_folder()
    assert started == ["b.flac"]


async def test_settings_queue_raises_last_file_stops(started, player):
    player(path="c.flac", folder=["a.flac", "b.flac", "c.flac"], raises=True)
    await gui_server.play_next_in_folder()
    assert started == []


# repeat が None で返ってきたとき

async def test_repeat_none_treated_as_none(started, player):
    mozart = AsyncMock()
    mozart.get_settings_queue.return_value = SimpleNamespace(repeat=None, shuffle=False)
    gui_server.local_play["path"] = "a.flac"
    gui_server.local_play["folder"] = ["a.flac", "b.flac", "c.flac"]
    gui_server.live.mozart = mozart
    await gui_server.play_next_in_folder()
    assert started == ["b.flac"]


# start_local_file が失敗したとき

async def test_start_local_file_raises_swallowed(monkeypatch):
    async def failing_start(client, rel, device_ip):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(gui_server, "start_local_file", failing_start)
    monkeypatch.setattr(gui_server, "resolve_host", lambda _: "192.168.1.10")
    gui_server.local_play["path"] = "a.flac"
    gui_server.local_play["folder"] = ["a.flac", "b.flac", "c.flac"]
    mozart = AsyncMock()
    mozart.get_settings_queue.return_value = SimpleNamespace(repeat="none", shuffle=False)
    gui_server.live.mozart = mozart

    await gui_server.play_next_in_folder()


async def test_start_local_file_raises_prints_error(monkeypatch, capsys):
    async def failing_start(client, rel, device_ip):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(gui_server, "start_local_file", failing_start)
    monkeypatch.setattr(gui_server, "resolve_host", lambda _: "192.168.1.10")
    gui_server.local_play["path"] = "a.flac"
    gui_server.local_play["folder"] = ["a.flac", "b.flac", "c.flac"]
    mozart = AsyncMock()
    mozart.get_settings_queue.return_value = SimpleNamespace(repeat="none", shuffle=False)
    gui_server.live.mozart = mozart

    await gui_server.play_next_in_folder()
    captured = capsys.readouterr()
    assert "auto-advance failed" in captured.out
