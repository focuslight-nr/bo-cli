import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--device",
        action="store_true",
        default=False,
        help="ネットワーク上の実機に接続するテストも実行する",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--device"):
        return
    skip = pytest.mark.skip(reason="実機テスト。実行するには --device を付ける")
    for item in items:
        if "device" in item.keywords:
            item.add_marker(skip)
