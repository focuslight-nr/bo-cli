from types import SimpleNamespace
import gui_server

async def test_get_queue_settings_success(cli, mock_client):
    mock_client.get_settings_queue.return_value = SimpleNamespace(repeat="all", shuffle=True)
    resp = await cli.get("/api/queue-settings")
    assert resp.status == 200
    body = await resp.json()
    assert body == {"repeat": "all", "shuffle": True}

async def test_get_queue_settings_shuffle_none_coerced(cli, mock_client):
    mock_client.get_settings_queue.return_value = SimpleNamespace(repeat="all", shuffle=None)
    resp = await cli.get("/api/queue-settings")
    assert resp.status == 200
    body = await resp.json()
    assert body["shuffle"] is False

async def test_post_queue_settings_repeat_only(cli, mock_client):
    resp = await cli.post("/api/queue-settings", json={"repeat": "track"})
    assert resp.status == 200
    call_kwargs = mock_client.set_settings_queue.call_args.kwargs
    settings = call_kwargs["play_queue_settings"]
    assert settings.repeat == "track"
    assert settings.shuffle is None

async def test_post_queue_settings_shuffle_only(cli, mock_client):
    resp = await cli.post("/api/queue-settings", json={"shuffle": True})
    assert resp.status == 200
    call_kwargs = mock_client.set_settings_queue.call_args.kwargs
    settings = call_kwargs["play_queue_settings"]
    assert settings.shuffle is True
    assert settings.repeat is None

async def test_post_queue_settings_both_fields(cli, mock_client):
    resp = await cli.post("/api/queue-settings", json={"repeat": "all", "shuffle": False})
    assert resp.status == 200
    call_kwargs = mock_client.set_settings_queue.call_args.kwargs
    settings = call_kwargs["play_queue_settings"]
    assert settings.repeat == "all"
    assert settings.shuffle is False

async def test_post_queue_settings_shuffle_truthy_int(cli, mock_client):
    resp = await cli.post("/api/queue-settings", json={"shuffle": 1})
    assert resp.status == 200
    call_kwargs = mock_client.set_settings_queue.call_args.kwargs
    settings = call_kwargs["play_queue_settings"]
    assert settings.shuffle is True

async def test_post_queue_settings_invalid_repeat_raises_502(cli, mock_client):
    resp = await cli.post("/api/queue-settings", json={"repeat": "bogus"})
    assert resp.status == 502
    body = await resp.json()
    assert "invalid repeat" in body["error"]
    mock_client.set_settings_queue.assert_not_awaited()

async def test_post_queue_settings_empty_body_allowed(cli, mock_client):
    resp = await cli.post("/api/queue-settings", json={})
    assert resp.status == 200
    call_kwargs = mock_client.set_settings_queue.call_args.kwargs
    settings = call_kwargs["play_queue_settings"]
    assert settings.repeat is None
    assert settings.shuffle is None

async def test_get_volume_settings_success(cli, mock_client):
    default_obj = SimpleNamespace(level=30)
    maximum_obj = SimpleNamespace(level=90)
    mock_client.get_volume_settings.return_value = SimpleNamespace(default=default_obj, maximum=maximum_obj)
    resp = await cli.get("/api/volume-settings")
    assert resp.status == 200
    body = await resp.json()
    assert body == {"default": 30, "maximum": 90}

async def test_get_volume_settings_default_none(cli, mock_client):
    maximum_obj = SimpleNamespace(level=90)
    mock_client.get_volume_settings.return_value = SimpleNamespace(default=None, maximum=maximum_obj)
    resp = await cli.get("/api/volume-settings")
    assert resp.status == 200
    body = await resp.json()
    assert body["default"] is None

async def test_get_volume_settings_maximum_none(cli, mock_client):
    default_obj = SimpleNamespace(level=30)
    mock_client.get_volume_settings.return_value = SimpleNamespace(default=default_obj, maximum=None)
    resp = await cli.get("/api/volume-settings")
    assert resp.status == 200
    body = await resp.json()
    assert body["maximum"] is None

async def test_post_volume_settings_default_only(cli, mock_client):
    resp = await cli.post("/api/volume-settings", json={"default": 25})
    assert resp.status == 200
    call_kwargs = mock_client.set_volume_settings.call_args.kwargs
    settings = call_kwargs["volume_settings"]
    assert settings.default.level == 25
    assert settings.maximum is None

async def test_post_volume_settings_maximum_only(cli, mock_client):
    resp = await cli.post("/api/volume-settings", json={"maximum": 80})
    assert resp.status == 200
    call_kwargs = mock_client.set_volume_settings.call_args.kwargs
    settings = call_kwargs["volume_settings"]
    assert settings.maximum.level == 80
    assert settings.default is None

async def test_post_volume_settings_default_string_int(cli, mock_client):
    resp = await cli.post("/api/volume-settings", json={"default": "35"})
    assert resp.status == 200
    call_kwargs = mock_client.set_volume_settings.call_args.kwargs
    settings = call_kwargs["volume_settings"]
    assert settings.default.level == 35

async def test_post_volume_settings_default_null_skipped(cli, mock_client):
    resp = await cli.post("/api/volume-settings", json={"default": None})
    assert resp.status == 200
    call_kwargs = mock_client.set_volume_settings.call_args.kwargs
    settings = call_kwargs["volume_settings"]
    assert settings.default is None

async def test_post_volume_settings_empty_body_allowed(cli, mock_client):
    resp = await cli.post("/api/volume-settings", json={})
    assert resp.status == 200
    call_kwargs = mock_client.set_volume_settings.call_args.kwargs
    settings = call_kwargs["volume_settings"]
    assert settings.default is None
    assert settings.maximum is None

async def test_post_adjustments_bass_only(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={"bass": 3})
    assert resp.status == 200
    mock_client.set_sound_settings_adjustments_bass.assert_awaited_once()
    bass_arg = mock_client.set_sound_settings_adjustments_bass.call_args.kwargs["bass"]
    assert bass_arg.value == 3
    mock_client.set_sound_settings_adjustments_treble.assert_not_awaited()
    mock_client.set_sound_settings_adjustments_loudness.assert_not_awaited()

async def test_post_adjustments_treble_only(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={"treble": -2})
    assert resp.status == 200
    mock_client.set_sound_settings_adjustments_treble.assert_awaited_once()
    treble_arg = mock_client.set_sound_settings_adjustments_treble.call_args.kwargs["treble"]
    assert treble_arg.value == -2
    mock_client.set_sound_settings_adjustments_bass.assert_not_awaited()
    mock_client.set_sound_settings_adjustments_loudness.assert_not_awaited()

async def test_post_adjustments_loudness_true(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={"loudness": True})
    assert resp.status == 200
    mock_client.set_sound_settings_adjustments_loudness.assert_awaited_once()
    loudness_arg = mock_client.set_sound_settings_adjustments_loudness.call_args.kwargs["loudness"]
    assert loudness_arg.value is True
    mock_client.set_sound_settings_adjustments_bass.assert_not_awaited()
    mock_client.set_sound_settings_adjustments_treble.assert_not_awaited()

async def test_post_adjustments_loudness_false(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={"loudness": False})
    assert resp.status == 200
    mock_client.set_sound_settings_adjustments_loudness.assert_awaited_once()
    loudness_arg = mock_client.set_sound_settings_adjustments_loudness.call_args.kwargs["loudness"]
    assert loudness_arg.value is False
    mock_client.set_sound_settings_adjustments_bass.assert_not_awaited()
    mock_client.set_sound_settings_adjustments_treble.assert_not_awaited()

async def test_post_adjustments_all_fields(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={"bass": 1, "treble": 2, "loudness": True})
    assert resp.status == 200
    mock_client.set_sound_settings_adjustments_bass.assert_awaited_once()
    mock_client.set_sound_settings_adjustments_treble.assert_awaited_once()
    mock_client.set_sound_settings_adjustments_loudness.assert_awaited_once()

async def test_post_adjustments_empty_body_no_calls(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={})
    assert resp.status == 200
    mock_client.set_sound_settings_adjustments_bass.assert_not_awaited()
    mock_client.set_sound_settings_adjustments_treble.assert_not_awaited()
    mock_client.set_sound_settings_adjustments_loudness.assert_not_awaited()

async def test_post_adjustments_invalid_bass_type_raises_502(cli, mock_client):
    resp = await cli.post("/api/adjustments", json={"bass": "not a number"})
    assert resp.status == 502
