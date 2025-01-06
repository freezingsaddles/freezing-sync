from freezing.sync.config import Config


def test_config_present():
    assert Config.MAIN_TEAM is not None
