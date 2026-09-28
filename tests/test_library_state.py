from types import SimpleNamespace
import pytest
import gui_server

@pytest.fixture(autouse=True)
def reset_local_play():
    before = dict(gui_server.local_play)
    yield
    gui_server.local_play.clear()
    gui_server.local_play.update(before)

def make_state(level=30, muted=False, state="playing", source="spotify",
               artist="A", title="T", organization=None,
               progress=10, total_duration=200, art=None):
    volume = SimpleNamespace(level=SimpleNamespace(level=level) if level is not None else None,
                             muted=SimpleNamespace(muted=muted))
    meta = SimpleNamespace(artist_name=artist, title=title, organization=organization,
                           art=art or [])
    playback = SimpleNamespace(
        state=SimpleNamespace(value=state) if state else None,
        source=SimpleNamespace(type=SimpleNamespace(value=source)) if source else None,
        metadata=meta,
        progress=SimpleNamespace(progress=progress, total_duration=total_duration)
                 if progress is not None else None)
    return volume, playback

def set_state(mock_client, volume, playback):
    mock_client.get_current_volume.return_value = volume
    mock_client.get_playback_state.return_value = playback

# GET /api/library tests

async def test_library_root_no_path(cli, music_dir):
    resp = await cli.get("/api/library")
    assert resp.status == 200
    data = await resp.json()
    assert data["path"] == ""
    assert {"name": "album", "path": "album"} in data["dirs"]
    assert data["files"] == []

async def test_library_album_path(cli, music_dir):
    resp = await cli.get("/api/library?path=album")
    assert resp.status == 200
    data = await resp.json()
    assert {"name": "song.flac", "path": "album/song.flac"} in data["files"]

async def test_library_non_audio_ext_excluded(cli, music_dir):
    (music_dir / "album" / "cover.jpg").write_bytes(b"JPGDATA")
    resp = await cli.get("/api/library?path=album")
    assert resp.status == 200
    data = await resp.json()
    file_names = [f["name"] for f in data["files"]]
    assert "cover.jpg" not in file_names

async def test_library_dot_file_excluded(cli, music_dir):
    (music_dir / "album" / ".hidden.flac").write_bytes(b"HIDDEN")
    resp = await cli.get("/api/library?path=album")
    assert resp.status == 200
    data = await resp.json()
    file_names = [f["name"] for f in data["files"]]
    assert ".hidden.flac" not in file_names

async def test_library_dot_dir_excluded(cli, music_dir):
    (music_dir / ".cache").mkdir()
    resp = await cli.get("/api/library")
    assert resp.status == 200
    data = await resp.json()
    dir_names = [d["name"] for d in data["dirs"]]
    assert ".cache" not in dir_names

async def test_library_sorting_case_insensitive(cli, music_dir):
    (music_dir / "Bravo").mkdir()
    (music_dir / "alpha").mkdir()
    (music_dir / "Charlie").mkdir()
    resp = await cli.get("/api/library")
    assert resp.status == 200
    data = await resp.json()
    dir_names = [d["name"] for d in data["dirs"]]
    assert dir_names == sorted(dir_names, key=str.lower)
    assert [n for n in dir_names if n in ("alpha", "Bravo", "Charlie")] == [
        "alpha",
        "Bravo",
        "Charlie",
    ]

async def test_library_all_audio_exts_recognized(cli, music_dir):
    ext_dir = music_dir / "exts"
    ext_dir.mkdir()
    for ext in gui_server.AUDIO_EXTS:
        (ext_dir / f"file{ext}").write_bytes(b"DUMMY")
    resp = await cli.get(f"/api/library?path=exts")
    assert resp.status == 200
    data = await resp.json()
    file_names = {f["name"] for f in data["files"]}
    expected = {f"file{ext}" for ext in gui_server.AUDIO_EXTS}
    assert file_names == expected

async def test_library_uppercase_ext_included(cli, music_dir):
    (music_dir / "album" / "Track.FLAC").write_bytes(b"FLAC")
    resp = await cli.get("/api/library?path=album")
    assert resp.status == 200
    data = await resp.json()
    file_names = [f["name"] for f in data["files"]]
    assert "Track.FLAC" in file_names

async def test_library_file_path_returns_404(cli, music_dir):
    resp = await cli.get("/api/library?path=album/song.flac")
    assert resp.status == 404
    data = await resp.json()
    assert "not a directory" in data["error"]

async def test_library_missing_path_returns_404(cli, music_dir):
    resp = await cli.get("/api/library?path=nope")
    assert resp.status == 404

async def test_library_outside_root_returns_403(cli, music_dir):
    resp = await cli.get("/api/library?path=../..")
    assert resp.status == 403

async def test_library_missing_music_root_returns_404(cli, tmp_path, monkeypatch):
    monkeypatch.setattr(gui_server, "music_root", lambda: tmp_path / "gone")
    resp = await cli.get("/api/library")
    assert resp.status == 404
    data = await resp.json()
    assert "music dir not found" in data["error"]

# GET /api/state tests

async def test_state_full_payload(cli, mock_client):
    volume, playback = make_state()
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["state"] == "playing"
    assert data["source"] == "spotify"
    assert data["artist"] == "A"
    assert data["title"] == "T"
    assert data["volume"] == 30
    assert data["muted"] is False

async def test_state_muted_true(cli, mock_client):
    volume, playback = make_state(muted=True)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["muted"] is True

async def test_state_volume_level_none(cli, mock_client):
    volume, playback = make_state(level=None)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["volume"] is None
    assert isinstance(data["muted"], bool)

async def test_state_playback_state_none(cli, mock_client):
    volume, playback = make_state(state=None)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["state"] is None

async def test_state_playback_source_none(cli, mock_client):
    volume, playback = make_state(source=None)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["source"] is None

async def test_state_playback_progress_none(cli, mock_client):
    volume, playback = make_state(progress=None)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["progress"] is None

async def test_state_duration_zero_falls_back_to_local(cli, mock_client):
    gui_server.local_play["duration"] = 321
    volume, playback = make_state(total_duration=0)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["duration"] == 321

async def test_state_duration_nonzero_wins_over_local(cli, mock_client):
    gui_server.local_play["duration"] = 321
    volume, playback = make_state(total_duration=200)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["duration"] == 200

async def test_state_progress_none_falls_back_to_local_duration(cli, mock_client):
    gui_server.local_play["duration"] = 321
    volume, playback = make_state(progress=None)
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["duration"] == 321

async def test_state_art_none_falls_back_to_local(cli, mock_client):
    gui_server.local_play["art"] = "/media-art?v=x"
    volume, playback = make_state(art=[])
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["art"] == "/media-art?v=x"

async def test_state_art_remote_wins_over_local(cli, mock_client):
    gui_server.local_play["art"] = "/media-art?v=x"
    art_item = SimpleNamespace(key="640x640", url="https://cdn/x.jpg")
    volume, playback = make_state(art=[art_item])
    set_state(mock_client, volume, playback)
    resp = await cli.get("/api/state")
    assert resp.status == 200
    data = await resp.json()
    assert data["art"] == "https://cdn/x.jpg"
