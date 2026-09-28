from types import SimpleNamespace
import gui_server

def set_state(mock_client, title, artist="", source="netRadio", organization="Station"):
    mock_client.get_current_volume.return_value = SimpleNamespace(
        level=SimpleNamespace(level=30), muted=SimpleNamespace(muted=False))
    mock_client.get_playback_state.return_value = SimpleNamespace(
        state=SimpleNamespace(value="started"),
        source=SimpleNamespace(type=SimpleNamespace(value=source)) if source else None,
        metadata=SimpleNamespace(artist_name=artist, title=title,
                                 organization=organization, art=[]),
        progress=SimpleNamespace(progress=4, total_duration=None))

async def test_placeholder_title_becomes_none(cli, mock_client):
    set_state(mock_client, "Shonan Beach FM - offline", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] is None

async def test_placeholder_organization_unchanged(cli, mock_client):
    set_state(mock_client, "Shonan Beach FM - offline", artist="", source="netRadio", organization="Station")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["organization"] == "Station"

async def test_airtime_offline_title_becomes_none(cli, mock_client):
    set_state(mock_client, "Airtime - offline", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] is None

async def test_uppercase_offline_title_becomes_none(cli, mock_client):
    set_state(mock_client, "SOMETHING - OFFLINE", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] is None

async def test_whitespace_surrounded_offline_title_becomes_none(cli, mock_client):
    set_state(mock_client, "  Shonan Beach FM - offline  ", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] is None

async def test_none_artist_treated_as_no_artist(cli, mock_client):
    set_state(mock_client, "Shonan Beach FM - offline", artist=None, source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] is None

async def test_title_kept_when_artist_present(cli, mock_client):
    set_state(mock_client, "Shonan Beach FM - offline", artist="Some Artist", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "Shonan Beach FM - offline"

async def test_title_kept_when_source_not_netradio(cli, mock_client):
    set_state(mock_client, "Shonan Beach FM - offline", artist="", source="spotify")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "Shonan Beach FM - offline"

async def test_title_kept_when_no_separator(cli, mock_client):
    set_state(mock_client, "Offline", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "Offline"

async def test_title_kept_when_offline_not_at_end(cli, mock_client):
    set_state(mock_client, "Offline - Remastered", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "Offline - Remastered"

async def test_title_kept_when_just_offline(cli, mock_client):
    set_state(mock_client, "offline", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "offline"

async def test_title_kept_for_ordinary_track(cli, mock_client):
    set_state(mock_client, "Artist - Song", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "Artist - Song"

async def test_title_kept_when_going_offline(cli, mock_client):
    set_state(mock_client, "Going offline", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == "Going offline"

async def test_empty_title_returns_empty_string(cli, mock_client):
    set_state(mock_client, "", artist="", source="netRadio")
    resp = await cli.get("/api/state")
    body = await resp.json()
    assert body["title"] == ""

def test_unit_placeholder_true():
    assert gui_server.is_offline_placeholder("X - offline", "", "netRadio") is True

def test_unit_placeholder_false_with_artist():
    assert gui_server.is_offline_placeholder("X - offline", "A", "netRadio") is False

def test_unit_placeholder_false_wrong_source():
    assert gui_server.is_offline_placeholder("X - offline", "", "spotify") is False

def test_unit_placeholder_false_none_title():
    assert gui_server.is_offline_placeholder(None, "", "netRadio") is False

def test_unit_placeholder_false_empty_title():
    assert gui_server.is_offline_placeholder("", "", "netRadio") is False


# ---- ライブ更新経路(WebSocket)。build_state を通らないので別に検証する ----


def make_meta(title, artist="", organization="Station"):
    return SimpleNamespace(
        title=title, artist_name=artist, organization=organization, art=[]
    )


def test_live_metadata_drops_offline_placeholder():
    state = {"source": "netRadio"}
    gui_server.apply_metadata(state, make_meta("Shonan Beach FM - offline"), "10.0.0.5")
    assert state["title"] is None


def test_live_metadata_keeps_organization():
    state = {"source": "netRadio"}
    gui_server.apply_metadata(
        state, make_meta("Shonan Beach FM - offline", organization="Shonan Beach FM 78.9"), "10.0.0.5"
    )
    assert state["organization"] == "Shonan Beach FM 78.9"


def test_live_metadata_keeps_real_track():
    state = {"source": "netRadio"}
    gui_server.apply_metadata(state, make_meta("Song", artist="Artist"), "10.0.0.5")
    assert state["title"] == "Song"
    assert state["artist"] == "Artist"


def test_live_metadata_keeps_offline_title_when_artist_present():
    state = {"source": "netRadio"}
    gui_server.apply_metadata(state, make_meta("X - offline", artist="Artist"), "10.0.0.5")
    assert state["title"] == "X - offline"


def test_live_metadata_keeps_offline_title_on_other_sources():
    state = {"source": "spotify"}
    gui_server.apply_metadata(state, make_meta("X - offline"), "10.0.0.5")
    assert state["title"] == "X - offline"


def test_live_metadata_without_known_source_keeps_title():
    # ソース未確定(初期状態取得に失敗した等)ではフィルタをかけない
    state = {}
    gui_server.apply_metadata(state, make_meta("X - offline"), "10.0.0.5")
    assert state["title"] == "X - offline"


def test_live_metadata_falls_back_to_local_art(monkeypatch):
    monkeypatch.setitem(gui_server.local_play, "art", "/media-art?v=x")
    state = {"source": "netRadio"}
    gui_server.apply_metadata(state, make_meta("Song", artist="A"), "10.0.0.5")
    assert state["art"] == "/media-art?v=x"
