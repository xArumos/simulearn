"""Batched reply generation with fixed decoding settings, and loss on the real child replies."""
from __future__ import annotations

import math

import torch

from src.train.collator import IGNORE, PadCollator, encode_example


def build_prompt_ids(tok, messages: list[dict], max_prompt_tokens: int) -> list[int]:
    """Chat-template the context (everything but the real reply), dropping the oldest turns if too long."""
    msgs = list(messages[:-1])
    while True:
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True)
        if hasattr(ids, "keys"):  # some versions return a BatchEncoding
            ids = ids["input_ids"]
        if len(ids) <= max_prompt_tokens or len(msgs) <= 2:
            return list(ids)[-max_prompt_tokens:]
        msgs = [msgs[0]] + msgs[2:]


@torch.no_grad()
def generate_replies(model, tok, examples: list[dict], *, temperature=0.7, top_p=0.9, max_new_tokens=60,
                     seed=1234, batch_size=32, max_length=512) -> list[str]:
    """One reply per example. Deterministic for a fixed seed, batch size, and example order."""
    tok.padding_side = "left"
    prompts = [build_prompt_ids(tok, e["messages"], max_length - max_new_tokens) for e in examples]
    # Batch similar lengths together (less padding); the order is fixed, so this stays reproducible.
    order = sorted(range(len(prompts)), key=lambda i: (len(prompts[i]), i))
    out: list[str] = [""] * len(prompts)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    for s in range(0, len(order), batch_size):
        idx = order[s:s + batch_size]
        n = max(len(prompts[i]) for i in idx)
        ids = torch.full((len(idx), n), tok.pad_token_id, dtype=torch.long)
        mask = torch.zeros((len(idx), n), dtype=torch.long)
        for row, i in enumerate(idx):
            p = prompts[i]
            ids[row, n - len(p):] = torch.tensor(p)
            mask[row, n - len(p):] = 1
        gen = model.generate(
            input_ids=ids.to(model.device), attention_mask=mask.to(model.device),
            do_sample=True, temperature=temperature, top_p=top_p, max_new_tokens=max_new_tokens,
            pad_token_id=tok.pad_token_id,
        )
        for row, i in enumerate(idx):
            out[i] = tok.decode(gen[row, n:], skip_special_tokens=True).strip()
    return out


@torch.no_grad()
def target_loss(model, tok, examples: list[dict], batch_size=16, max_length=512) -> dict:
    """Mean loss per child-reply token (system and adult turns masked), and its perplexity.

    Perplexity = exp(loss): roughly "how many equally likely choices the model is torn between per
    token" when predicting the real child's words. Lower = the real replies look less surprising.
    """
    tok.padding_side = "right"
    enc = [e for e in (encode_example(tok, ex["messages"], max_length) for ex in examples) if e]
    coll = PadCollator(tok.pad_token_id)
    total, count = 0.0, 0
    for s in range(0, len(enc), batch_size):
        b = coll(enc[s:s + batch_size])
        b = {k: v.to(model.device) for k, v in b.items()}
        logits = model(input_ids=b["input_ids"], attention_mask=b["attention_mask"]).logits
        shift_labels = b["labels"][:, 1:]
        keep = shift_labels != IGNORE
        # Only the child-reply positions, in float32. Converting the full (batch x seq x vocab) logits
        # to float32 needs several GB and made Windows' GPU driver spill into system RAM and reset.
        sel = logits[:, :-1][keep].float()
        del logits
        loss = torch.nn.functional.cross_entropy(sel, shift_labels[keep], reduction="sum")
        total += loss.item()
        count += int(keep.sum())
    mean = total / max(count, 1)
    return {"loss": mean, "perplexity": math.exp(mean), "n_examples": len(enc), "n_tokens": count}
