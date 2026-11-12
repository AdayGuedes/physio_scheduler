import importlib

import pytest

import config


@pytest.fixture
def load_config(monkeypatch):
    def load(enable_dev_seed):
        monkeypatch.setenv("ENABLE_DEV_SEED", enable_dev_seed)
        return importlib.reload(config).Config

    yield load

    monkeypatch.undo()
    importlib.reload(config)


@pytest.mark.parametrize(
    "value, expected",
    [("1", True), ("true", False), ("0", False), ("", False)],
)
def test_enable_dev_seed_only_accepts_one(load_config, value, expected):
    assert load_config(value).ENABLE_DEV_SEED is expected
