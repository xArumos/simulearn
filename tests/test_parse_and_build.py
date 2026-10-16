from collections import Counter

from src.data.build_examples import BuildConfig, build_turns, examples_from_turns
from src.data.parse_chat import age_to_months, parse_text
from tests.fake_chat import FAKE


def test_age_to_months():
    assert age_to_months("4;06.12") == 54
    assert age_to_months("3;11.") == 47
    assert age_to_months("5;") == 60
    assert age_to_months("") is None


def test_parse_headers_and_tiers():
    t = parse_text(FAKE, "Eng-NA/Fake/a.cha", "Fake", "Eng-NA")
    assert t.primary_language == "eng"
    assert [p.code for p in t.target_children] == ["CHI"]
    assert t.participants["CHI"].age_months == 62
    assert t.participants["CHI"].birth == "01-JAN-2000"
    assert t.types == "long, toyplay, TD"
    assert len(t.utterances) == 11                      # %mor skipped
    mot = t.utterances[3]
    assert mot.text == "okay , apples and juice ."      # continuation line joined, bullet removed
    assert (mot.start_ms, mot.end_ms) == (4600, 6000)


def _build(**kw):
    t = parse_text(FAKE, "Eng-NA/Fake/a.cha", "Fake", "Eng-NA")
    cfg = BuildConfig(break_speakers={"Fake": ["ROB"]}, **kw)
    c = Counter()
    turns, info = build_turns(t, "CHI", cfg, c)
    return turns, info, c


def test_turns_merge_silence_and_breaks():
    turns, info, c = _build()
    assert info["timed"]
    roles = [x.role for x in turns]
    assert roles == ["user", "assistant", "user", "assistant", "user", "assistant", "break", "assistant", "user", "assistant"]
    # Two consecutive child utterances are merged; the 2.2 s gap puts a token inside the turn.
    assert turns[1].text == "apples. <SILENCE FOR 2 SECONDS> and juice."
    assert not turns[3].target_ok                        # xxx turn kept as a placeholder
    assert turns[3].text == "(unintelligible)"
    assert turns[9].text == "<SILENCE FOR 3 SECONDS> no it's mine!"


def test_examples_targets_and_context():
    turns, _, c = _build(context_turns=6)
    exs = examples_from_turns(turns, "SYS", 6, c)
    idx = [i for i, _ in exs]
    # turn 3 (xxx) dropped, turn 7 (after robot break) dropped
    assert idx == [1, 5, 9]
    assert c["target_dropped_unusable"] == 1
    assert c["target_dropped_no_adult_before"] == 1
    _, msgs = exs[-1]
    # Context stops at the robot break: only the turns after it are left
    assert [m["role"] for m in msgs] == ["system", "assistant", "user", "assistant"]
    assert [m["content"] for m in msgs[1:3]] == ["hi robot.", "can I have some?"]
    _, msgs = exs[1]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert len(msgs) - 2 == 5                            # turns 0-4 (only 5 exist before turn 5)
    assert msgs[-2]["role"] == "user"
    assert msgs[-1]["content"] == "I said thank you."


def test_short_context_window():
    turns, _, c = _build()
    exs = examples_from_turns(turns, "SYS", 4, c)
    _, msgs = exs[1]
    assert [m["role"] for m in msgs] == ["system", "assistant", "user", "assistant", "user", "assistant"]
