async def test_devices_endpoint(cli):
    resp = await cli.get("/api/devices")
    assert resp.status == 200
    assert await resp.json() == {"devices": {"リビング": "192.168.1.10"}, "default": "リビング"}
