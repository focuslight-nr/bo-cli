import datetime
import json
import gui_server


async def test_get_night_defaults(cli):
    resp = await cli.get("/api/night")
    assert resp.status == 200
    data = await resp.json()
    assert data == {
        "enabled": False,
        "start": "22:00",
        "end": "07:00",
        "maxVolume": 40,
        "standbyAt": "",
    }


async def test_put_night_max_volume_clamped_high(cli):
    resp = await cli.put("/api/night", json={"maxVolume": 150})
    assert resp.status == 200
    data = await resp.json()
    assert data["maxVolume"] == 100


async def test_put_night_max_volume_clamped_low(cli):
    resp = await cli.put("/api/night", json={"maxVolume": -5})
    assert resp.status == 200
    data = await resp.json()
    assert data["maxVolume"] == 0


async def test_put_night_max_volume_string_to_int(cli):
    resp = await cli.put("/api/night", json={"maxVolume": "30"})
    assert resp.status == 200
    data = await resp.json()
    assert data["maxVolume"] == 30
    assert isinstance(data["maxVolume"], int)


async def test_put_night_partial_update(cli):
    resp = await cli.put("/api/night", json={"enabled": True, "start": "23:30"})
    assert resp.status == 200
    data = await resp.json()
    assert data["enabled"] is True
    assert data["start"] == "23:30"
    assert data["end"] == "07:00"


async def test_put_night_persists_to_file(cli, gui_config):
    await cli.put("/api/night", json={"maxVolume": 50})
    config = json.loads(gui_config.read_text())
    assert config["night"]["maxVolume"] == 50


async def test_put_night_invalid_time_returns_500(cli):
    resp = await cli.put("/api/night", json={"start": "25:00"})
    assert resp.status == 500


async def test_put_night_empty_standby_at_ok(cli):
    resp = await cli.put("/api/night", json={"standbyAt": ""})
    assert resp.status == 200


async def test_put_night_valid_standby_at_roundtrips(cli):
    resp = await cli.put("/api/night", json={"standbyAt": "02:15"})
    assert resp.status == 200
    data = await resp.json()
    assert data["standbyAt"] == "02:15"


async def test_put_night_empty_body_returns_defaults(cli):
    resp = await cli.put("/api/night", json={})
    assert resp.status == 200
    data = await resp.json()
    assert data["maxVolume"] == 40


async def test_put_tts_volume_clamped_high(cli):
    resp = await cli.put("/api/tts-volume", json={"volume": 120})
    assert resp.status == 200
    data = await resp.json()
    assert data == {"volume": 100}


async def test_put_tts_volume_none_persists_and_returns_none(cli):
    resp = await cli.put("/api/tts-volume", json={"volume": None})
    assert resp.status == 200
    data = await resp.json()
    assert data == {"volume": None}

    get_resp = await cli.get("/api/tts-volume")
    assert get_resp.status == 200
    get_data = await get_resp.json()
    assert get_data == {"volume": None}


async def test_put_tts_volume_valid_persists(cli):
    resp = await cli.put("/api/tts-volume", json={"volume": 55})
    assert resp.status == 200

    get_resp = await cli.get("/api/tts-volume")
    assert get_resp.status == 200
    data = await get_resp.json()
    assert data["volume"] == 55


async def test_put_music_dir_empty_returns_400(cli):
    resp = await cli.put("/api/music-dir", json={"musicDir": ""})
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


async def test_put_music_dir_whitespace_only_returns_400(cli):
    resp = await cli.put("/api/music-dir", json={"musicDir": "   "})
    assert resp.status == 400


async def test_put_music_dir_missing_key_returns_400(cli):
    resp = await cli.put("/api/music-dir", json={})
    assert resp.status == 400


async def test_put_music_dir_nonexistent_path_exists_false(cli, gui_config):
    path = "/definitely/not/a/real/dir"
    resp = await cli.put("/api/music-dir", json={"musicDir": path})
    assert resp.status == 200
    data = await resp.json()
    assert data["exists"] is False
    config = json.loads(gui_config.read_text())
    assert config["musicDir"] == path


async def test_put_music_dir_real_path_exists_true(cli, tmp_path):
    resp = await cli.put("/api/music-dir", json={"musicDir": str(tmp_path)})
    assert resp.status == 200
    data = await resp.json()
    assert data["exists"] is True


async def test_put_favorites_dict_returns_400(cli):
    resp = await cli.put("/api/favorites", json={})
    assert resp.status == 400


async def test_put_favorites_invalid_type_returns_400(cli):
    resp = await cli.put("/api/favorites", json=[{"type": "bogus", "value": "x"}])
    assert resp.status == 400


async def test_put_favorites_missing_value_returns_400(cli):
    resp = await cli.put("/api/favorites", json=[{"type": "radio"}])
    assert resp.status == 400


async def test_put_favorites_defaults_name_to_value(cli):
    entry = {"type": "uri", "value": "http://x/y"}
    resp = await cli.put("/api/favorites", json=[entry])
    assert resp.status == 200
    data = await resp.json()
    assert data[0]["name"] == "http://x/y"


async def test_put_favorites_valid_list_persists_and_returns(cli):
    entries = [
        {"type": "radio", "value": "1234567890123456"},
        {"type": "source", "value": "s1"},
    ]
    resp = await cli.put("/api/favorites", json=entries)
    assert resp.status == 200

    get_resp = await cli.get("/api/favorites")
    assert get_resp.status == 200
    data = await get_resp.json()
    assert len(data) == 2


async def test_put_favorites_empty_list_returns_empty(cli):
    resp = await cli.put("/api/favorites", json=[])
    assert resp.status == 200

    get_resp = await cli.get("/api/favorites")
    assert get_resp.status == 200
    data = await get_resp.json()
    assert data == []


def test_in_window_same_day_inside():
    now = datetime.time(12, 0)
    start = datetime.time(9, 0)
    end = datetime.time(17, 0)
    assert gui_server.in_window(now, start, end) is True


def test_in_window_same_day_before():
    now = datetime.time(8, 59)
    start = datetime.time(9, 0)
    end = datetime.time(17, 0)
    assert gui_server.in_window(now, start, end) is False


def test_in_window_same_day_at_start():
    now = datetime.time(9, 0)
    start = datetime.time(9, 0)
    end = datetime.time(17, 0)
    assert gui_server.in_window(now, start, end) is True


def test_in_window_same_day_at_end():
    now = datetime.time(17, 0)
    start = datetime.time(9, 0)
    end = datetime.time(17, 0)
    assert gui_server.in_window(now, start, end) is False


def test_in_window_overnight_inside_evening():
    now = datetime.time(23, 30)
    start = datetime.time(22, 0)
    end = datetime.time(7, 0)
    assert gui_server.in_window(now, start, end) is True


def test_in_window_overnight_inside_morning():
    now = datetime.time(3, 0)
    start = datetime.time(22, 0)
    end = datetime.time(7, 0)
    assert gui_server.in_window(now, start, end) is True


def test_in_window_overnight_outside():
    now = datetime.time(12, 0)
    start = datetime.time(22, 0)
    end = datetime.time(7, 0)
    assert gui_server.in_window(now, start, end) is False


def _radio(value):
    return [{"type": "radio", "value": value, "name": "ラジオ"}]


async def test_favorites_put_accepts_16_digit_radio_id(cli):
    resp = await cli.put("/api/favorites", json=_radio("1234567890123456"))
    assert resp.status == 200
    body = await resp.json()
    assert body[0]["value"] == "1234567890123456"


async def test_favorites_put_rejects_short_radio_id(cli):
    resp = await cli.put("/api/favorites", json=_radio("1234"))
    assert resp.status == 400
    assert "16 digits" in (await resp.json())["error"]


async def test_favorites_put_rejects_long_radio_id(cli):
    resp = await cli.put("/api/favorites", json=_radio("12345678901234567"))
    assert resp.status == 400


async def test_favorites_put_rejects_non_digit_radio_id(cli):
    resp = await cli.put("/api/favorites", json=_radio("abcdefghijklmnop"))
    assert resp.status == 400


async def test_favorites_put_rejected_radio_id_does_not_overwrite(cli):
    await cli.put("/api/favorites", json=_radio("1234567890123456"))
    await cli.put("/api/favorites", json=_radio("999"))
    kept = await (await cli.get("/api/favorites")).json()
    assert kept[0]["value"] == "1234567890123456"


async def test_favorites_put_still_accepts_uri_and_source(cli):
    resp = await cli.put(
        "/api/favorites",
        json=[
            {"type": "uri", "value": "http://x/a.mp3"},
            {"type": "source", "value": "spotify"},
        ],
    )
    assert resp.status == 200
    assert len(await resp.json()) == 2
