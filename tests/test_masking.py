"""Label-masking test (CLAUDE.md §7.4): the unmasked label tokens must decode to exactly the child reply."""
import pytest

from src.train.collator import IGNORE, PadCollator, encode_example

MODELS = ["Qwen/Qwen2.5-1.5B-Instruct", "HuggingFaceTB/SmolLM2-360M-Instruct"]

MSGS = [
    {"role": "system", "content": "You are a 5-year-old child talking with a caregiver. Reply the way a real child of that age would."},
    {"role": "user", "content": "what are you building?"},
    {"role": "assistant", "content": "a tower."},
    {"role": "user", "content": "<SILENCE FOR 3 SECONDS> how tall is it gonna be?"},
    {"role": "assistant", "content": "um really really tall! <SILENCE FOR 2 SECONDS> like the sky."},
]


def _tok(name):
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained(name)
    except Exception as e:  # offline and not cached
        pytest.skip(f"tokenizer {name} unavailable: {e}")


@pytest.mark.parametrize("model", MODELS)
def test_only_child_reply_is_learned(model):
    tok = _tok(model)
    enc = encode_example(tok, MSGS, max_length=512)
    learned = [t for t, l in zip(enc["input_ids"], enc["labels"]) if l != IGNORE]
    assert tok.decode(learned, skip_special_tokens=True) == MSGS[-1]["content"]
    # The end-of-turn token is learned too, so the model learns when to stop.
    assert learned[-1] in {tok.eos_token_id, tok.convert_tokens_to_ids("<|im_end|>")}
    # Labels are a contiguous block at the end; the earlier child turn ("a tower.") is not learned.
    first = next(i for i, l in enumerate(enc["labels"]) if l != IGNORE)
    assert all(l != IGNORE for l in enc["labels"][first:])
    assert "a tower" not in tok.decode(learned)


@pytest.mark.parametrize("model", MODELS)
def test_truncation_keeps_target(model):
    tok = _tok(model)
    long_msgs = [MSGS[0]] + [{"role": r, "content": "blah " * 60} for r in ["user", "assistant"] * 4] + MSGS[-2:]
    enc = encode_example(tok, long_msgs, max_length=160)
    assert enc is not None and len(enc["input_ids"]) <= 160
    learned = [t for t, l in zip(enc["input_ids"], enc["labels"]) if l != IGNORE]
    assert tok.decode(learned, skip_special_tokens=True) == MSGS[-1]["content"]
    assert enc["n_context_turns_used"] < 10


def test_pad_collator():
    batch = PadCollator(pad_token_id=0)([{"input_ids": [5, 6, 7], "labels": [IGNORE, 6, 7]}, {"input_ids": [5], "labels": [5]}])
    assert batch["input_ids"].tolist() == [[5, 6, 7], [5, 0, 0]]
    assert batch["labels"].tolist() == [[IGNORE, 6, 7], [5, IGNORE, IGNORE]]
    assert batch["attention_mask"].tolist() == [[1, 1, 1], [1, 0, 0]]
