"""Refuse models from countries of concern before anything is downloaded or loaded (POLICIES.md §1).

`check_model(name, adapter=None)` raises `ProhibitedModelError` when the model name, or the base model named in an
adapter's `adapter_config.json`, matches the deny list below. It only looks at strings and small JSON files, so it is
safe to call before any `from_pretrained`. Stdlib only, so `scripts/slurm/submit_all.sh` can run it on a login node:

    python -m src.utils.model_policy MODEL_NAME [--adapter PATH]     # exit 0 = allowed, 3 = prohibited

The list is not complete (POLICIES.md says so too). Passing this check does not make a model acceptable: every new
model still needs its developer checked and recorded in DECISIONS.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Hugging Face organizations (the part before "/"), compared case-insensitively. An entry ending in "*" is a prefix.
DENIED_ORGS = (
    "qwen", "alibaba-nlp", "alibaba-pai", "deepseek-ai", "thudm", "zai-org", "moonshotai", "01-ai", "baichuan-inc",
    "internlm", "shanghai_ai_laboratory", "minimaxai", "tencent", "tencentarc", "baidu", "paddlepaddle", "bytedance*",
)
# Substrings anywhere in the name (lower-cased). Catches re-uploads, local copies and distills under other orgs,
# e.g. "someone/DeepSeek-R1-Distill-Llama-8B" or "/models/qwen2.5-1.5b".
DENIED_SUBSTRINGS = ("qwen", "deepseek", "chatglm", "internlm", "baichuan", "hunyuan", "minimax")

POLICY_POINTER = "See POLICIES.md §1: UF prohibits LLMs from countries of concern, fine-tunes and adapters included."


class ProhibitedModelError(ValueError):
    """A model (or an adapter's base model) is on the deny list."""


def denied_reason(name: str) -> str | None:
    """Why `name` is denied, or None if it matches nothing on the list."""
    low = str(name).strip().lower()
    if "/" in low and not low.startswith(("/", ".")):
        org = low.split("/", 1)[0]
        for entry in DENIED_ORGS:
            if (entry.endswith("*") and org.startswith(entry[:-1])) or org == entry:
                return f"organization '{name.split('/', 1)[0]}' is on the deny list"
    for sub in DENIED_SUBSTRINGS:
        if sub in low:
            return f"name contains '{sub}'"
    return None


def is_denied(name: str) -> bool:
    return denied_reason(name) is not None


def adapter_base_model(adapter: str | Path) -> str | None:
    """`base_model_name_or_path` from `<adapter>/adapter_config.json`, or None if there is no such file."""
    cfg = Path(adapter) / "adapter_config.json"
    if not cfg.is_file():
        return None
    return json.loads(cfg.read_text()).get("base_model_name_or_path")


def check_model(name: str, adapter: str | Path | None = None) -> None:
    """Raise ProhibitedModelError if `name`, or the base model of `adapter`, is denied. Call before loading."""
    reason = denied_reason(name)
    if reason:
        raise ProhibitedModelError(f"refusing to load model '{name}': {reason}. {POLICY_POINTER}")
    if adapter:
        base = adapter_base_model(adapter)
        if base and is_denied(base):
            raise ProhibitedModelError(
                f"refusing to load adapter '{adapter}': it was trained on '{base}' ({denied_reason(base)}). "
                f"{POLICY_POINTER}")
        # Our run folders name the model (experiments/<stamp>_qwen1.5b_.../adapter). Only the last two parts are
        # checked, so an unrelated parent folder can't trigger a refusal.
        tail = "/".join(Path(adapter).parts[-2:])
        if any(s in tail.lower() for s in DENIED_SUBSTRINGS):
            raise ProhibitedModelError(
                f"refusing to load adapter '{adapter}': its path names a prohibited model. {POLICY_POINTER}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exit 3 if a model is prohibited by POLICIES.md §1.")
    ap.add_argument("model")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--context", default="", help="added to the error message, e.g. the config path")
    a = ap.parse_args(argv)
    try:
        check_model(a.model, a.adapter)
    except ProhibitedModelError as e:
        print(f"error: {a.context + ': ' if a.context else ''}{e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
