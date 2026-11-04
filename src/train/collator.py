"""Tokenize chat examples with loss only on the final child (assistant) reply.

How the mask is built (works for any chat template, tested on Qwen2.5 and SmolLM2):
    prompt_str = template(messages[:-1], add_generation_prompt=True)   # ...<|im_start|>assistant\n
    full_str   = template(messages)                                     # prompt + reply + <|im_end|>\n
    completion = full_str[len(prompt_str):].rstrip()                    # reply + <|im_end|>
prompt tokens get label -100 (ignored by the loss); completion tokens are learned, including the
end-of-turn token so the model learns to stop. Trailing whitespace after it is not part of the input.

If an example is longer than max_length, the oldest context turns are dropped (keeping the system
prompt and at least the last adult turn). If it still does not fit, the example is skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch

IGNORE = -100


def _render(tok, messages, add_generation_prompt=False) -> str:
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=add_generation_prompt)


def encode_example(tok, messages: list[dict], max_length: int = 512) -> dict | None:
    msgs = list(messages)
    while True:
        prompt_str = _render(tok, msgs[:-1], add_generation_prompt=True)
        full_str = _render(tok, msgs)
        if not full_str.startswith(prompt_str):
            raise ValueError("Chat template: full conversation does not start with the generation prompt.")
        completion = full_str[len(prompt_str):].rstrip()
        p_ids = tok(prompt_str, add_special_tokens=False)["input_ids"]
        c_ids = tok(completion, add_special_tokens=False)["input_ids"]
        if len(p_ids) + len(c_ids) <= max_length:
            break
        # Drop the oldest context turn after the system prompt; keep >= 1 user turn before the target.
        if len(msgs) <= 3:
            return None
        msgs = [msgs[0]] + msgs[2:]
        while len(msgs) > 3 and msgs[1]["role"] != "user":
            msgs = [msgs[0]] + msgs[2:]
    return {
        "input_ids": p_ids + c_ids,
        "labels": [IGNORE] * len(p_ids) + c_ids,
        "n_context_turns_used": len(msgs) - 2,
    }


@dataclass
class PadCollator:
    pad_token_id: int

    def __call__(self, batch: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        n = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), n), self.pad_token_id, dtype=torch.long)
        labels = torch.full((len(batch), n), IGNORE, dtype=torch.long)
        mask = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):
            L = len(b["input_ids"])
            ids[i, :L] = torch.tensor(b["input_ids"])
            labels[i, :L] = torch.tensor(b["labels"])
            mask[i, :L] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": mask}
