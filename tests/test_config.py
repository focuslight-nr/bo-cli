import json
import pytest
import bo

@pytest.fixture(autouse=True)
def config_path(tmp_path, monkeypatch):
    p = tmp_path / "devices.json"
    monkeypatch.setattr(bo, "CONFIG_PATH", p)
    return p

def write_config(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def test_load_config_file_does_not_exist(config_path):
    assert bo.load_config() == {"default": None, "devices": {}}

def test_load_config_file_exists_valid_json(config_path):
    data = {"default": "Beosound", "devices": {"Beosound": {"ip": "192.168.1.10"}}}
    write_config(config_path, data)
    assert bo.load_config() == data

def test_save_config_creates_parent_and_file(config_path):
    config = {"default": None, "devices": {}}
    bo.save_config(config)
    assert config_path.exists()
    reloaded = json.loads(config_path.read_text())
    assert reloaded == config

def test_save_config_non_ascii_unescaped(config_path):
    config = {"default": None, "devices": {"リビング": {"ip": "192.168.1.20"}}}
    bo.save_config(config)
    raw_text = config_path.read_text()
    assert "リビング" in raw_text

def test_cmd_default_name_present_updates_config(config_path):
    data = {"default": None, "devices": {"Beosound": {"ip": "192.168.1.10"}}}
    write_config(config_path, data)
    bo.cmd_default("Beosound")
    reloaded = json.loads(config_path.read_text())
    assert reloaded["default"] == "Beosound"

def test_cmd_default_name_absent_raises_system_exit(config_path):
    data = {"default": None, "devices": {"Beosound": {"ip": "192.168.1.10"}}}
    write_config(config_path, data)
    with pytest.raises(SystemExit) as exc_info:
        bo.cmd_default("UnknownDevice")
    assert "UnknownDevice" in str(exc_info.value)

def test_cmd_default_absent_name_does_not_modify_config(config_path):
    original_data = {"default": None, "devices": {"Beosound": {"ip": "192.168.1.10"}}}
    write_config(config_path, original_data)
    with pytest.raises(SystemExit):
        bo.cmd_default("UnknownDevice")
    reloaded = json.loads(config_path.read_text())
    assert reloaded == original_data

def test_resolve_host_target_none_default_set_returns_ip(config_path):
    data = {"default": "Beosound", "devices": {"Beosound": {"ip": "192.168.1.10"}}}
    write_config(config_path, data)
    assert bo.resolve_host(None) == "192.168.1.10"

def test_resolve_host_target_none_default_none_raises_system_exit(config_path):
    data = {"default": None, "devices": {}}
    write_config(config_path, data)
    with pytest.raises(SystemExit):
        bo.resolve_host(None)

def test_resolve_host_target_registered_device_returns_ip(config_path):
    data = {"default": None, "devices": {"Beosound": {"ip": "192.168.1.10"}}}
    write_config(config_path, data)
    assert bo.resolve_host("Beosound") == "192.168.1.10"

def test_resolve_host_target_unregistered_ip_returns_as_is(config_path):
    data = {"default": None, "devices": {}}
    write_config(config_path, data)
    assert bo.resolve_host("192.168.1.50") == "192.168.1.50"

def test_resolve_host_target_unregistered_name_returns_as_is(config_path):
    data = {"default": None, "devices": {}}
    write_config(config_path, data)
    assert bo.resolve_host("unknown") == "unknown"
