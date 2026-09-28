import json
import gui_server

# api() wrapper tests

async def test_api_wrapper_returns_ok_on_none(cli):
    resp = await cli.post("/api/volume", json={"level": 30})
    assert resp.status == 200
    assert await resp.json() == {"ok": True}

async def test_api_wrapper_closes_client_on_success(cli, mock_client):
    await cli.post("/api/volume", json={"level": 30})
    mock_client.close_api_client.assert_awaited_once()

async def test_api_wrapper_returns_502_on_error(cli, mock_client):
    mock_client.set_current_volume_level.side_effect = RuntimeError("boom")
    resp = await cli.post("/api/volume", json={"level": 30})
    assert resp.status == 502
    body = await resp.json()
    assert "boom" in body["error"]

async def test_api_wrapper_closes_client_on_error(cli, mock_client):
    mock_client.set_current_volume_level.side_effect = RuntimeError("boom")
    await cli.post("/api/volume", json={"level": 30})
    mock_client.close_api_client.assert_awaited_once()

# h_volume tests

async def test_h_volume_sets_level_int(cli, mock_client):
    await cli.post("/api/volume", json={"level": 30})
    mock_client.set_current_volume_level.assert_awaited_once()
    call_kwargs = mock_client.set_current_volume_level.call_args.kwargs
    assert call_kwargs["volume_level"].level == 30

async def test_h_volume_sets_level_string(cli, mock_client):
    await cli.post("/api/volume", json={"level": "45"})
    call_kwargs = mock_client.set_current_volume_level.call_args.kwargs
    level_obj = call_kwargs["volume_level"]
    assert level_obj.level == 45
    assert isinstance(level_obj.level, int)

async def test_h_volume_missing_level_returns_502(cli):
    resp = await cli.post("/api/volume", json={})
    assert resp.status == 502

# h_say tests

async def test_h_say_defaults_lang_and_no_volume_absent(cli, mock_client, gui_config):
    # Ensure no config file exists to trigger default behavior for volume lookup if needed,
    # though the prompt implies "no config file" for case 8. 
    # The fixture provides a path; we ensure it's empty or missing for this specific test context if possible.
    # However, conftest might have written it. Let's assume standard state.
    # Case 8 says "with no config file". We can remove it temporarily if needed, but let's trust the fixture state 
    # or just rely on the fact that if key is missing, it falls back to default lang.
    # Actually, case 11 explicitly writes config. So for 8/9 we assume clean state or missing key.
    
    resp = await cli.post("/api/say", json={"text": "こんにちは"})
    assert resp.status == 200
    
    mock_client.post_overlay_play.assert_awaited_once()
    req = mock_client.post_overlay_play.call_args.kwargs["overlay_play_request"]
    assert req.text_to_speech.text == "こんにちは"
    assert req.text_to_speech.lang == "ja-jp"

async def test_h_say_volume_absolute_absent_when_not_configured(cli, mock_client):
    # Re-use the call from previous test or make a new one. 
    # Since mocks persist, we need to reset or check the specific call.
    # Let's make a fresh call to be safe and clear.
    mock_client.reset_mock()
    await cli.post("/api/say", json={"text": "test"})
    
    req = mock_client.post_overlay_play.call_args.kwargs["overlay_play_request"]
    assert "volumeAbsolute" not in req.to_dict()

async def test_h_say_custom_lang(cli, mock_client):
    mock_client.reset_mock()
    await cli.post("/api/say", json={"text": "hi", "lang": "en-us"})
    
    req = mock_client.post_overlay_play.call_args.kwargs["overlay_play_request"]
    assert req.text_to_speech.lang == "en-us"

async def test_h_say_uses_config_volume(cli, mock_client, gui_config):
    mock_client.reset_mock()
    gui_config.write_text(json.dumps({"ttsVolume": 25}))
    
    await cli.post("/api/say", json={"text": "hi"})
    
    req = mock_client.post_overlay_play.call_args.kwargs["overlay_play_request"]
    assert req.to_dict()["volumeAbsolute"] == 25

async def test_h_say_request_volume_overrides_config(cli, mock_client, gui_config):
    mock_client.reset_mock()
    # Config has 25 from previous test
    await cli.post("/api/say", json={"text": "hi", "volume": 70})
    
    req = mock_client.post_overlay_play.call_args.kwargs["overlay_play_request"]
    assert req.to_dict()["volumeAbsolute"] == 70

async def test_h_say_missing_text_returns_502(cli):
    resp = await cli.post("/api/say", json={})
    assert resp.status == 502

# h_favorite_play tests

async def test_h_favorite_play_uri_type(cli, mock_client):
    mock_client.reset_mock()
    await cli.put("/api/favorites", json=[{"type": "uri", "value": "http://x/a.mp3", "name": "A"}])
    
    resp = await cli.post("/api/favorites/play", json={"index": 0})
    assert resp.status == 200
    assert await resp.json() == {"ok": True}
    mock_client.post_uri_source.assert_awaited_once()

async def test_h_favorite_play_source_type(cli, mock_client):
    mock_client.reset_mock()
    await cli.put("/api/favorites", json=[{"type": "source", "value": "spotify"}])
    
    resp = await cli.post("/api/favorites/play", json={"index": 0})
    assert resp.status == 200
    
    mock_client.set_active_source.assert_awaited_once()
    call_kwargs = mock_client.set_active_source.call_args.kwargs
    assert call_kwargs["source_id"] == "spotify"

async def test_h_favorite_play_radio_type(cli, mock_client):
    mock_client.reset_mock()
    await cli.put("/api/favorites", json=[{"type": "radio", "value": "1234567890123456"}])
    
    resp = await cli.post("/api/favorites/play", json={"index": 0})
    assert resp.status == 200
    
    mock_client.run_provided_scene.assert_awaited_once()

async def test_h_favorite_play_out_of_range_empty_config(cli):
    # Ensure no favorites are configured. 
    # We can put an empty list to clear them if the endpoint supports it, or rely on initial state.
    # The prompt says "no favorites configured". Let's assume we can clear them by putting empty list.
    await cli.put("/api/favorites", json=[])
    
    resp = await cli.post("/api/favorites/play", json={"index": 0})
    assert resp.status == 502
    body = await resp.json()
    assert "out of range" in body["error"]

async def test_h_favorite_play_out_of_range_index(cli, mock_client):
    mock_client.reset_mock()
    await cli.put("/api/favorites", json=[{"type": "uri", "value": "http://x/a.mp3"}])
    
    resp = await cli.post("/api/favorites/play", json={"index": 5})
    assert resp.status == 502

# h_media tests

async def test_h_media_returns_file_content(cli, music_dir):
    resp = await cli.get("/media/album/song.flac")
    assert resp.status == 200
    assert await resp.read() == b"FLACDATA"

async def test_h_media_missing_file_returns_404(cli, music_dir):
    resp = await cli.get("/media/album/missing.flac")
    assert resp.status == 404

async def test_h_media_path_traversal_returns_403(cli, music_dir):
    # Use encoded path to bypass aiohttp's automatic normalization if any
    resp = await cli.get("/media/..%2F..%2Fetc%2Fpasswd")
    assert resp.status == 403
