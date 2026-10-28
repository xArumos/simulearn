"""Chat with the trained 6-year-old in the terminal (works on a Mac, a GPU PC, or CPU only).

    python scripts/chat_age6.py --adapter experiments/age6_A_smol360m_cpu/adapter

You type the adult's lines; the model answers as a 6-year-old. Same system prompt and decoding as
evaluation (temperature 0.7, top-p 0.9, max 60 new tokens), last 6 turns of history.
Type /reset to start a new conversation, /quit to stop. No CHILDES text is shipped with this script.
Needs: pip install torch transformers peft (downloads the base model from Hugging Face on first run).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

SYSTEM = "You are a 6-year-old child talking with a caregiver. Reply the way a real child of that age would."
CONTEXT_TURNS = 6


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load(adapter: Path, device: str):
    base = json.loads((adapter / "adapter_config.json").read_text())["base_model_name_or_path"]
    tok = AutoTokenizer.from_pretrained(base)
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(base, dtype=dtype).to(device)
    model = PeftModel.from_pretrained(model, str(adapter)).eval()
    return tok, model, base


@torch.no_grad()
def reply(tok, model, history: list[dict], adult_line: str, seed: int) -> str:
    msgs = [{"role": "system", "content": SYSTEM}] + history[-CONTEXT_TURNS:] + [{"role": "user", "content": adult_line}]
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
    torch.manual_seed(seed)
    out = model.generate(**ids, do_sample=True, temperature=0.7, top_p=0.9, max_new_tokens=60,
                         pad_token_id=tok.pad_token_id or tok.eos_token_id)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="experiments/age6_A_smol360m_cpu/adapter")
    ap.add_argument("--say", nargs="*", help="non-interactive: adult lines to send in order, then exit")
    a = ap.parse_args()
    device = pick_device()
    tok, model, base = load(Path(a.adapter), device)
    print(f"6-year-old ready ({base} + {a.adapter}, on {device}). You are the adult. /reset, /quit.\n")
    history: list[dict] = []
    lines = iter(a.say) if a.say is not None else None
    seed = 1234
    while True:
        try:
            line = next(lines) if lines is not None else input("Adult: ").strip()
        except (StopIteration, EOFError):
            break
        if lines is not None:
            print(f"Adult: {line}")
        if line == "/quit":
            break
        if line == "/reset":
            history = []
            print("(new conversation)\n")
            continue
        if not line:
            continue
        child = reply(tok, model, history, line, seed)
        seed += 1
        print(f"Child: {child}\n")
        history += [{"role": "user", "content": line}, {"role": "assistant", "content": child}]


if __name__ == "__main__":
    main()
