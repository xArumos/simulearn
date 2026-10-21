from src.eval.metrics import compute_metrics, distinct_n, is_loop, reply_flags, words


def test_words_ignore_silence_token():
    assert words("<SILENCE FOR 3 SECONDS> I goed home.") == ["i", "goed", "home"]


def test_flags():
    f = reply_flags("Sure! As a 5-year-old, I love the park!")
    assert f["meta"]
    f = reply_flags("um I I want it")
    assert f["filler"] and f["repetition"] and not f["meta"]
    assert reply_flags("yeah.")["short_answer"]
    assert reply_flags("Mom: what about you?")["continues_other_side"]
    assert reply_flags("<SILENCE FOR 2 SECONDS> no.")["silence"]
    assert reply_flags("<SILENCE 2 sec> no.")["silence_malformed"]
    assert reply_flags("me and him goed")["nonstandard"]
    assert reply_flags("")["empty"]


def test_loop_and_distinct():
    assert is_loop("a b c a b c a b c".split())
    assert is_loop("no no no no".split())
    assert not is_loop("no no no".split())
    assert distinct_n(["a b", "a c"], 1) == 0.75


def test_identical_systems_have_zero_gap():
    real = ["yeah.", "I goed to the park.", "um no.", "<SILENCE FOR 2 SECONDS> mhm."]
    m = compute_metrics(real, real)
    assert m["length_ks"] == 0 and m["length_wasserstein"] == 0 and m["child_marker_gap"] == 0
