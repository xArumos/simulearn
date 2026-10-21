"""Cleaning rules. Every CHAT line here is invented for the test, not copied from CHILDES."""
from collections import Counter

import pytest

from src.data.clean import CleanConfig, clean_utterance


def clean(s, **kw):
    c = Counter()
    r = clean_utterance(s, c, CleanConfig(**kw) if kw else None)
    return r, c


@pytest.mark.parametrize("raw, expected, rule", [
    ("I goed [: went] to the zoo .", "I goed to the zoo.", "replacement[:]"),
    ("&=laughs that's funny !", "that's funny!", "action&="),
    ("&-um I want the red one .", "um I want the red one.", "filler&-"),
    ("I want [/] I want juice .", "I want I want juice.", "repetition[/]"),
    ("<the doggy> [//] the cat ran .", "the doggy the cat ran.", "retrace[//]"),
    ("is that a moose [?] ?", "is that a moose?", "uncertain[?]"),
    ("we went to the (.) store .", "we went to the store.", "pause(.)"),
    ("and then +...", "and then...", "terminator_incomplete"),
    ("look at the doggie@c .", "look at the doggie.", "word_form@"),
    ("I'm goin(g) home .", "I'm goin home.", "omitted_sounds()"),
    ("that 0is mine .", "that mine.", "omitted_word0"),
    ("no:: I don't wanna .", "no I don't wanna.", "lengthening:"),
    ("I like ice_cream .", "I like ice cream.", "compound_"),
    ("<you know> [>] it's big .", "you know it's big.", "overlap[<>]"),
    ("[^ points at book] that one .", "that one.", "comment[^]"),
    ("she runned [* m:+ed] fast .", "she runned fast.", "error[*]"),
    ("bye [=! whispers] .", "bye.", "paralinguistic[=!]"),
    ("+\" I'm a dinosaur .", "I'm a dinosaur.", "linker"),
    ("find the &~ro rocket .", "find the rocket.", "fragment&+~"),
    ("you know „ Mommy ?", "you know, Mommy?", "tag_marker"),
])
def test_rules(raw, expected, rule):
    r, c = clean(raw)
    assert r.text == expected
    assert c[rule] >= 1
    assert r.target_ok()


def test_keeps_child_forms_and_fillers():
    r, _ = clean("&-uh me and him goed swimming .")
    assert r.text == "uh me and him goed swimming."


def test_unintelligible_flagged_and_removed():
    r, c = clean("I want xxx please .")
    assert r.text == "I want please."
    assert r.unintelligible and not r.target_ok()
    assert c["unintelligible_xxx"] == 1
    r, _ = clean("yyy yyy .")
    assert r.empty and not r.target_ok()


def test_zero_utterance_is_empty():
    r, c = clean("0 [=! cries] .")
    assert r.empty
    assert c["empty_after_cleaning"] == 1


def test_foreign_and_reading_flags():
    r, _ = clean("[- spa] uno dos .")
    assert r.foreign and not r.target_ok()
    r, _ = clean("the cat sat on the mat . [+ read]")
    assert r.reading and not r.target_ok()
    assert r.text == "the cat sat on the mat."
    r, _ = clean("whee ! [+ nr:play]")
    assert r.target_ok() and r.text == "whee!"


def test_fragments_can_be_kept():
    r, _ = clean("find the &~ro rocket .", keep_fragments=True)
    assert r.text == "find the ro rocket."


def test_interrupted_question():
    r, _ = clean("where did you +/?")
    assert r.text == "where did you...?"


def test_only_punctuation_is_empty():
    r, _ = clean("&=nods .")
    assert r.empty
