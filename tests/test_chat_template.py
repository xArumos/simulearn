"""The chat-template date is pinned: the same conversation renders to the same prompt on any day.

Llama 3.2's template writes "Today Date: <today>" into the system header unless date_string is passed, so
without the pin a prompt (and what the model was trained on) would change from day to day.
"""
from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("transformers")
pytest.importorskip("tokenizers")

from transformers.utils import chat_template_utils  # noqa: E402

from src.train.collator import IGNORE, PadCollator, encode_example  # noqa: E402
from src.utils.chat_template import CHAT_TEMPLATE_DATE, apply_chat_template  # noqa: E402
from tests.fake_llama import fake_llama_tokenizer  # noqa: E402

MSGS = [
    {"role": "system", "content": "You are a 5-year-old child talking with a caregiver."},
    {"role": "user", "content": "what are you making?"},
    {"role": "assistant", "content": "a big boat."},
]


def _on_day(monkeypatch, day: dt.datetime):
    class FrozenDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return day

    monkeypatch.setattr(chat_template_utils, "datetime", FrozenDatetime)


def test_fake_template_really_uses_today_when_unpinned(monkeypatch):
    """Guards the test itself: without the pin, the fake (like Llama 3.2) changes with the clock."""
    tok = fake_llama_tokenizer()
    _on_day(monkeypatch, dt.datetime(2026, 1, 5))
    a = tok.apply_chat_template(MSGS, tokenize=False)
    _on_day(monkeypatch, dt.datetime(2027, 6, 9))
    b = tok.apply_chat_template(MSGS, tokenize=False)
    assert a != b and "05 Jan 2026" in a


@pytest.mark.parametrize("gen", [False, True])
def test_pinned_prompt_is_the_same_on_different_days(monkeypatch, gen):
    tok = fake_llama_tokenizer()
    msgs = MSGS[:-1] if gen else MSGS
    _on_day(monkeypatch, dt.datetime(2026, 1, 5))
    a = apply_chat_template(tok, msgs, tokenize=False, add_generation_prompt=gen)
    a_ids = apply_chat_template(tok, msgs, tokenize=True, add_generation_prompt=gen)
    _on_day(monkeypatch, dt.datetime(2027, 6, 9))
    b = apply_chat_template(tok, msgs, tokenize=False, add_generation_prompt=gen)
    b_ids = apply_chat_template(tok, msgs, tokenize=True, add_generation_prompt=gen)
    assert a == b and a_ids == b_ids
    assert f"Today Date: {CHAT_TEMPLATE_DATE}" in a


def test_training_and_eval_prompts_use_the_pin(monkeypatch):
    """The collator (training, eval loss) and build_prompt_ids (generation) both go through the pinned helper."""
    torch = pytest.importorskip("torch")  # noqa: F841
    from src.eval.generate import build_prompt_ids

    tok = fake_llama_tokenizer()
    outs = []
    for day in (dt.datetime(2026, 1, 5), dt.datetime(2027, 6, 9)):
        _on_day(monkeypatch, day)
        outs.append((encode_example(tok, MSGS, 512)["input_ids"], build_prompt_ids(tok, MSGS, 512)))
    assert outs[0] == outs[1]
    enc_ids, prompt_ids = outs[0]
    assert CHAT_TEMPLATE_DATE in tok.decode(prompt_ids)
    assert enc_ids[:len(prompt_ids)] == prompt_ids  # training prompt == generation prompt


def test_llama_style_masking_learns_eot_and_padding_never_leaks():
    """Llama has no pad token, so load_tokenizer sets pad = eos = <|eot_id|>. The learned end-of-turn token
    is the same id as padding; labels must keep it for real replies and ignore every padded position."""
    tok = fake_llama_tokenizer()
    assert tok.pad_token is None
    tok.pad_token = tok.eos_token  # what src.utils.modeling.load_tokenizer does
    eot = tok.convert_tokens_to_ids("<|eot_id|>")
    assert tok.pad_token_id == eot

    enc = encode_example(tok, MSGS, 512)
    learned = [t for t, lab in zip(enc["input_ids"], enc["labels"]) if lab != IGNORE]
    assert tok.decode(learned, skip_special_tokens=True) == "a big boat."
    assert learned[-1] == eot and learned.count(eot) == 1

    short = encode_example(tok, [MSGS[0], MSGS[1], {"role": "assistant", "content": "no."}], 512)
    batch = PadCollator(tok.pad_token_id)([enc, short])
    n_short = len(short["input_ids"])
    assert (batch["labels"][1, n_short:] == IGNORE).all()  # padding is never learned
    assert batch["labels"][1, n_short - 1].item() == eot  # the real end of turn still is
    assert batch["attention_mask"][1].sum().item() == n_short
