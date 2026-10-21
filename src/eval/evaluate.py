"""Evaluate one model config: generate replies, compute §9.1 metrics, save everything to experiments/<run_id>/.

    python -m src.eval.evaluate --config configs/phase0/qwen1.5b_default.yaml [--max-examples 200] [--check-repro 32]

Writes: config.yaml, README.md (hypothesis), samples.jsonl (git-ignored, has CHILDES text), metrics.json.
Training (src/train/sft_lora.py) calls evaluate_model() on the trained model in the same process.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime
from pathlib import Path

import torch
import yaml

from src.eval.generate import generate_replies, target_loss
from src.eval.metrics import compute_metrics, vocab_from_replies
from src.utils.config import load_config, resolve
from src.utils.modeling import load_model, load_tokenizer

STRONG_PROMPT = ("You are a {age}-year-old child talking with a grown-up. Talk exactly like a real {age}-year-old: "
                 "short and simple, often just a few words, sometimes 'um', 'yeah', 'no', or 'I don't know'. "
                 "Never sound like an adult or an assistant. Only say what the child says.")


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def subsample(rows: list[dict], n: int | None, seed: int) -> list[dict]:
    if not n or n >= len(rows):
        return rows
    rng = random.Random(seed)
    return sorted(rng.sample(rows, n), key=lambda e: e["id"])


def with_system(examples: list[dict], system: str) -> list[dict]:
    return [{**e, "messages": [{"role": "system", "content": system}] + e["messages"][1:]} for e in examples]


def make_run_dir(cfg: dict, run_id: str | None) -> Path:
    run_id = run_id or f"{datetime.now():%Y%m%d-%H%M}_{cfg['run_name']}"
    out = resolve(cfg.get("experiments_dir", "experiments")) / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    if not (out / "README.md").exists():
        (out / "README.md").write_text(f"# {run_id}\n\n**Hypothesis:** {cfg.get('hypothesis', '(none)')}\n")
    return out


def eval_examples(cfg: dict, max_examples: int | None = None) -> tuple[list[dict], dict]:
    ev, data = cfg["eval"], cfg["data"]
    bdir = resolve(data["processed_dir"]) / data["bucket"]
    examples = subsample(read_jsonl(bdir / f"{ev['split']}.jsonl"), max_examples or ev.get("max_examples"), ev.get("sample_seed", 42))
    if ev.get("prompt_variant", "default") == "strong":
        examples = with_system(examples, STRONG_PROMPT.format(age=cfg.get("age_label", 5)))
    train_vocab = vocab_from_replies([e["messages"][-1]["content"] for e in read_jsonl(bdir / "train.jsonl")])
    return examples, train_vocab


def evaluate_model(model, tok, cfg: dict, out: Path, max_examples: int | None = None, check_repro: int = 0) -> dict:
    ev, mcfg = cfg["eval"], cfg["model"]
    examples, train_vocab = eval_examples(cfg, max_examples)
    model.eval()
    torch.cuda.reset_peak_memory_stats()
    gen_kw = {k: ev[k] for k in ["temperature", "top_p", "max_new_tokens", "seed", "batch_size", "max_length"] if k in ev}

    t0 = time.time()
    replies = generate_replies(model, tok, examples, **gen_kw)
    gen_s = time.time() - t0
    repro = None
    if check_repro:
        a = generate_replies(model, tok, examples[:check_repro], **gen_kw)
        b = generate_replies(model, tok, examples[:check_repro], **gen_kw)
        repro = {"n": check_repro, "identical": a == b}

    metrics = compute_metrics(replies, [e["messages"][-1]["content"] for e in examples], train_vocab)
    if ev.get("compute_loss", True):
        metrics["target_loss"] = target_loss(model, tok, examples, ev.get("loss_batch_size", 4), ev.get("max_length", 512))
    metrics["run"] = {"run_id": out.name, "model": mcfg["name"], "adapter": mcfg.get("adapter"), "split": ev["split"],
                      "bucket": cfg["data"]["bucket"], "prompt_variant": ev.get("prompt_variant", "default"),
                      "generation_seconds": round(gen_s, 1), "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
                      "reproducible": repro, "decoding": gen_kw}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    with open(out / "samples.jsonl", "w", encoding="utf-8") as f:
        for e, r in zip(examples, replies):
            f.write(json.dumps({"id": e["id"], "context_last": e["messages"][-2]["content"],
                                "reference": e["messages"][-1]["content"], "generated": r}, ensure_ascii=False) + "\n")
    g, ref = metrics["generated"], metrics["reference"]
    print(f"{out.name}: n={metrics['n']} mean_words {g['mean_words']:.2f} (real {ref['mean_words']:.2f}) "
          f"KS {metrics['length_ks']:.3f} degenerate {metrics['degeneration_rate']:.3f} marker_gap {metrics['child_marker_gap']:.3f} "
          f"loss {metrics.get('target_loss', {}).get('loss', float('nan')):.3f} gen {gen_s:.0f}s repro {repro}", flush=True)
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--max-examples", type=int, default=None, help="override eval.max_examples")
    ap.add_argument("--check-repro", type=int, default=0, help="generate the first N twice and check they are identical")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--adapter", default=None, help="override model.adapter (path to a trained LoRA adapter)")
    ap.add_argument("--seed", type=int, default=None, help="override eval.seed (to measure sampling noise)")
    a = ap.parse_args()
    cfg = load_config(resolve(a.config))
    if a.adapter:
        cfg["model"]["adapter"] = a.adapter
    if a.seed is not None:
        cfg["eval"]["seed"] = a.seed
    out = make_run_dir(cfg, a.run_id)
    tok = load_tokenizer(cfg["model"]["name"])
    model = load_model(cfg["model"])
    evaluate_model(model, tok, cfg, out, a.max_examples, a.check_repro)
    print(f"RUN_DIR {out}")


if __name__ == "__main__":
    main()
