from src.data.silence import SilenceConfig, gaps_ms, is_timed, silence_token

CFG = SilenceConfig()


def test_threshold_and_rounding():
    assert silence_token(1999, CFG) is None
    assert silence_token(2000, CFG) == "<SILENCE FOR 2 SECONDS>"
    assert silence_token(2499, CFG) == "<SILENCE FOR 2 SECONDS>"
    assert silence_token(2500, CFG) == "<SILENCE FOR 3 SECONDS>"   # half rounds up
    assert silence_token(None, CFG) is None


def test_cap():
    assert silence_token(45_000, CFG) == "<SILENCE FOR 10 SECONDS>"


def test_configurable_threshold_and_disable():
    assert silence_token(1500, SilenceConfig(threshold_s=1.0)) == "<SILENCE FOR 2 SECONDS>"
    assert silence_token(5000, SilenceConfig(enabled=False)) is None


def test_gaps_overlap_and_missing():
    times = [(0, 1000), (3500, 4000), (3900, 5000), (None, None), (9000, 9500)]
    assert gaps_ms(times) == [None, 2500, None, None, None]


def test_is_timed():
    assert is_timed([(0, 1), (2, 3)], CFG)
    assert not is_timed([(None, None), (None, None), (0, 1)], CFG)
    assert not is_timed([], CFG)
