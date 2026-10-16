"""Supervised fine-tuning with LoRA (or QLoRA when model.load_in_4bit is true).

    python -m src.train.sft_lora --config configs/phase1/<run>.yaml [--resume] [--run-id ID]

LoRA in one paragraph: instead of changing all ~1.5 billion weights of the model, we freeze them and
train small "adapter" matrices (rank r) added next to each linear layer. Only ~1% of the parameters
are trained, which fits on one consumer GPU and leaves the base model untouched. QLoRA is the same
idea, but the frozen base model is stored in 4-bit precision to save memory.

Loss is computed only on the child's reply tokens (src/train/collator.py, unit-tested).
We use the plain transformers Trainer, not TRL's SFTTrainer, so the masking is exactly our tested code
and not dependent on fast-changing TRL arguments (DECISIONS.md D5).

Outputs in experiments/<run_id>/: config.yaml, README.md, train.log (JSON lines), tb/ (TensorBoard),
checkpoints/ (git-ignored), adapter/ (best adapter, git-ignored weights), metrics.json + samples.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import EarlyStoppingCallback, Trainer, TrainerCallback, TrainingArguments, set_seed

from src.eval.evaluate import evaluate_model, make_run_dir, read_jsonl
from src.train.collator import PadCollator, encode_example
from src.utils.config import load_config, resolve
from src.utils.modeling import load_model, load_tokenizer


class ListDataset(torch.utils.data.Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


class JsonlLogger(TrainerCallback):
    """Append every Trainer log (loss, lr, eval_loss, ...) to train.log as one JSON object per line."""

    def __init__(self, path: Path):
        self.path = path
        self.t0 = time.time()

    def on_log(self, args, state, control, logs=None, **kw):
        rec = {"step": state.global_step, "epoch": round(state.epoch or 0, 3), "elapsed_s": round(time.time() - self.t0),
               "vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2), **(logs or {})}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)


def trim_context(messages: list[dict], n_turns: int | None) -> list[dict]:
    """Keep the system prompt + the last n_turns context turns + the target (only shortens)."""
    if not n_turns or len(messages) - 2 <= n_turns:
        return messages
    return [messages[0]] + messages[-(n_turns + 1):]


def load_split(cfg: dict, split: str, n: int | None, seed: int, tok, max_length: int, stats: dict) -> list[dict]:
    d = cfg["data"]
    rows = read_jsonl(resolve(d["processed_dir"]) / d["bucket"] / f"{split}.jsonl")
    if n and n < len(rows):
        rows = random.Random(seed).sample(rows, n)
    out = []
    for r in rows:
        enc = encode_example(tok, trim_context(r["messages"], d.get("context_turns")), max_length)
        if enc is None:
            stats[f"{split}_skipped_too_long"] = stats.get(f"{split}_skipped_too_long", 0) + 1
            continue
        enc.pop("n_context_turns_used")
        out.append(enc)
    stats[f"{split}_examples"] = len(out)
    stats[f"{split}_tokens"] = sum(len(e["input_ids"]) for e in out)
    stats[f"{split}_target_tokens"] = sum(sum(1 for l in e["labels"] if l != -100) for e in out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--resume", action="store_true", help="resume from the last checkpoint in the run dir")
    ap.add_argument("--no-eval", action="store_true", help="skip the generation evaluation after training")
    a = ap.parse_args()
    cfg = load_config(resolve(a.config))
    tr, lcfg, d = cfg["train"], cfg["lora"], cfg["data"]
    out = make_run_dir(cfg, a.run_id)
    os.environ["TENSORBOARD_LOGGING_DIR"] = str(out / "tb")
    set_seed(tr.get("seed", 42))

    tok = load_tokenizer(cfg["model"]["name"])
    stats: dict = {}
    max_len = tr.get("max_length", 512)
    train_rows = load_split(cfg, "train", d.get("max_train_examples"), d.get("sample_seed", 42), tok, max_len, stats)
    val_rows = load_split(cfg, "val", d.get("max_val_examples", 1000), d.get("sample_seed", 42), tok, max_len, stats)
    print("data:", json.dumps(stats), flush=True)

    model = load_model(cfg["model"], for_training=True)
    if cfg["model"].get("load_in_4bit"):
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=tr.get("gradient_checkpointing", True))
    model = get_peft_model(model, LoraConfig(
        r=lcfg["r"], lora_alpha=lcfg["alpha"], lora_dropout=lcfg.get("dropout", 0.05),
        target_modules=lcfg.get("target_modules", "all-linear"), bias="none", task_type="CAUSAL_LM"))
    trainable, total = model.get_nb_trainable_parameters()
    stats["trainable_params"], stats["total_params"] = trainable, total
    print(f"trainable params: {trainable:,} / {total:,} ({100 * trainable / total:.2f}%)", flush=True)
    if tr.get("gradient_checkpointing", True):
        model.enable_input_require_grads()

    steps_per_epoch = max(1, len(train_rows) // (tr["per_device_batch_size"] * tr["grad_accum"]))
    eval_every = tr.get("eval_steps") or max(10, steps_per_epoch // tr.get("evals_per_epoch", 4))
    args = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        per_device_train_batch_size=tr["per_device_batch_size"],
        per_device_eval_batch_size=tr.get("eval_batch_size", tr["per_device_batch_size"]),
        gradient_accumulation_steps=tr["grad_accum"],
        num_train_epochs=tr.get("epochs", 1),
        max_steps=tr.get("max_steps", -1),
        learning_rate=float(tr["lr"]),
        lr_scheduler_type=tr.get("scheduler", "cosine"),
        warmup_steps=tr.get("warmup", 0.03),
        weight_decay=tr.get("weight_decay", 0.0),
        bf16=True,
        gradient_checkpointing=tr.get("gradient_checkpointing", True),
        gradient_checkpointing_kwargs={"use_reentrant": False},
        eval_strategy="steps", eval_steps=eval_every,
        save_strategy="steps", save_steps=eval_every, save_total_limit=tr.get("save_total_limit", 3), save_only_model=False,
        load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
        logging_steps=tr.get("logging_steps", 10),
        report_to=["tensorboard"],
        seed=tr.get("seed", 42), data_seed=tr.get("seed", 42),
        remove_unused_columns=False, label_names=["labels"],
        dataloader_num_workers=tr.get("num_workers", 2),
    )
    callbacks = [JsonlLogger(out / "train.log")]
    if tr.get("early_stopping_patience"):
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=tr["early_stopping_patience"]))
    trainer = Trainer(model=model, args=args, data_collator=PadCollator(tok.pad_token_id),
                      train_dataset=ListDataset(train_rows), eval_dataset=ListDataset(val_rows), callbacks=callbacks)

    t0 = time.time()
    resume = a.resume and any((out / "checkpoints").glob("checkpoint-*"))
    result = trainer.train(resume_from_checkpoint=True if resume else None)
    stats["train_seconds"] = round(time.time() - t0)
    stats["train_result"] = result.metrics
    stats["best_checkpoint"] = trainer.state.best_model_checkpoint
    stats["best_eval_loss"] = trainer.state.best_metric
    stats["peak_vram_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
    model.save_pretrained(out / "adapter")  # best weights (load_best_model_at_end)
    (out / "train_stats.json").write_text(json.dumps(stats, indent=1))
    print("train:", json.dumps(stats), flush=True)

    if not a.no_eval:
        cfg["model"]["adapter"] = str(out / "adapter")
        model.config.use_cache = True
        evaluate_model(model, tok, cfg, out, check_repro=32)
    print(f"RUN_DIR {out}")


if __name__ == "__main__":
    main()
