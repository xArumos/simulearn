"""The child model without the web page: load the base model and age adapters, build the prompt, generate a reply.

Gradio-free, so the product backend can use it as well as the demo UI (src/demo/chat_demo.py). Same system prompt,
context window and decoding as training and evaluation. Nothing here imports gradio (tests/test_demo_core.py checks).
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import torch

from src.utils.chat_template import apply_chat_template
from src.utils.config import resolve
from src.utils.modeling import load_model, load_tokenizer
from src.utils.prompts import STRONG_PROMPT, SYSTEM_PROMPT

SILENCE_RE = re.compile(r"<SILENCE FOR (\d+) SECONDS>")


def find_adapters(cfg: dict, adapters_dir: str | Path | None = None) -> dict[int, dict]:
    """{age: {"path", "label"}} for the ages whose adapter folder exists. On the Space, adapters_dir
    (<dir>/age<N>/) replaces the local paths from the config."""
    found = {}
    for age, entry in sorted((cfg.get("adapters") or {}).items()):
        if adapters_dir:
            path = Path(adapters_dir) / f"age{age}"
        elif entry.get("path"):
            path = resolve(entry["path"])
        else:
            continue
        if (path / "adapter_config.json").is_file():
            found[int(age)] = {"path": path, "label": entry.get("label", "")}
    return found


def build_messages(system: str, history: list[dict], adult_line: str, context_turns: int) -> list[dict]:
    """Like training: the context is the last `context_turns` turns, the new adult line included."""
    keep = history[-(context_turns - 1):] if context_turns > 1 else []
    return [{"role": "system", "content": system}] + keep + [{"role": "user", "content": adult_line}]


def system_prompt(age: int, strong: bool = False) -> str:
    return (STRONG_PROMPT if strong else SYSTEM_PROMPT).format(age=age)


def pick_device(choice: str = "auto") -> str:
    """auto = cuda when a GPU is visible, else cpu (CUDA_VISIBLE_DEVICES="" simulates a machine without one)."""
    if choice == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if choice == "cuda" and not torch.cuda.is_available():
        raise SystemExit("--device cuda, but no CUDA GPU is visible. Use --device auto or cpu.")
    return choice


def render(text: str) -> str:
    """Show silence tags as a visible pause instead of raw text."""
    return SILENCE_RE.sub(lambda m: f"*(…pauses {m.group(1)} s…)*", text).strip() or "*(no reply)*"


def check_4bit(load_in_4bit: bool, device: str) -> None:
    """4-bit (bitsandbytes NF4) needs a real CUDA GPU at load time. ZeroGPU only lends one inside @spaces.GPU
    calls, so the model can't be quantized at startup there."""
    if not load_in_4bit:
        return
    if os.getenv("SPACES_ZERO_GPU"):
        raise SystemExit("4-bit loading (load_in_4bit) is not supported on the ZeroGPU Space: set load_in_4bit: false in "
                         "configs/demo.yaml and use a model that fits in bf16, or run the demo on the desktop GPU.")
    if device != "cuda":
        raise SystemExit(f"4-bit loading (load_in_4bit) needs a CUDA GPU, but the demo is running on {device}. Run it on a GPU "
                         "(--device cuda) or set load_in_4bit: false in configs/demo.yaml.")


class Demo:
    def __init__(self, cfg: dict, adapters: dict[int, dict], device: str | None = None):
        """device=None picks cuda if available. ZeroGPU passes "cuda" explicitly: its GPU only exists inside
        @spaces.GPU calls, but the model must be moved to cuda at startup."""
        if not adapters:
            raise SystemExit("No adapters found. Check configs/demo.yaml (or --adapters-dir).")
        self.cfg, self.adapters = cfg, adapters
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        cuda = self.device == "cuda"
        four_bit = bool(cfg.get("load_in_4bit"))
        check_4bit(four_bit, self.device)
        self.tok = load_tokenizer(cfg["base_model"])
        if four_bit:
            # 4-bit NF4 (DECISIONS.md D11), the form the QLoRA adapters were trained on. bitsandbytes 4-bit models
            # can't be moved with .to(), so the base is quantized straight onto the GPU and the adapters load there too.
            base = load_model({"name": cfg["base_model"], "dtype": "bfloat16", "device_map": "cuda", "load_in_4bit": True})
            adapter_device = "cuda"
        else:
            base = load_model({"name": cfg["base_model"], "dtype": "bfloat16" if cuda else "float32", "device_map": "cpu"})
            adapter_device = "cpu"
        from peft import PeftModel

        ages = sorted(adapters)
        self.model = PeftModel.from_pretrained(base, str(adapters[ages[0]]["path"]), adapter_name=f"age{ages[0]}",
                                               torch_device=adapter_device)
        for age in ages[1:]:
            self.model.load_adapter(str(adapters[age]["path"]), adapter_name=f"age{age}", torch_device=adapter_device)
        if not four_bit:
            # bf16/fp32: everything is loaded on the CPU and moved in one .to(): ZeroGPU's startup cuda emulation
            # can't read adapter files straight onto cuda ("No CUDA GPUs are available").
            self.model.to(self.device)
        self.model.eval()
        self.lock = threading.Lock()  # set_adapter + generate must not interleave between users
        self.seed = 1234

    @torch.no_grad()
    def reply(self, history: list[dict], adult_line: str, age: int | None, system: str) -> str:
        """age=None gives the untrained model (same weights with the LoRA add-on switched off)."""
        msgs = build_messages(system, history, adult_line, self.cfg["context_turns"])
        text = apply_chat_template(self.tok, msgs, tokenize=False, add_generation_prompt=True)
        ids = self.tok(text, return_tensors="pt").to(self.model.device)
        kw = dict(**ids, do_sample=True, pad_token_id=self.tok.pad_token_id, **self.cfg["decoding"])
        with self.lock:
            torch.manual_seed(self.seed)
            if age is None:
                with self.model.disable_adapter():
                    out = self.model.generate(**kw)
            else:
                self.model.set_adapter(f"age{age}")
                out = self.model.generate(**kw)
        return self.tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def timed(reply, request: tuple) -> tuple[str, float]:
    t0 = time.time()
    return reply(*request), time.time() - t0
