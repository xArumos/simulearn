"""GPU smoke test: load a model in bf16 (and optionally 4-bit), generate a few tokens, report VRAM.

Usage (inside WSL, after `source scripts/env_wsl.sh`):
    python scripts/gpu_smoke_test.py --model Qwen/Qwen2.5-1.5B-Instruct --also-4bit
"""
import argparse
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def run(model_name: str, quant: str) -> None:
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    kwargs = {"dtype": torch.bfloat16, "device_map": "cuda"}
    if quant == "4bit":
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
    load_s = time.time() - t0

    messages = [
        {"role": "system", "content": "You are a 5-year-old child talking with a caregiver. Reply the way a real child of that age would."},
        {"role": "user", "content": "What did you do at school today?"},
    ]
    inputs = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True).to("cuda")
    torch.manual_seed(42)
    t0 = time.time()
    out = model.generate(**inputs, max_new_tokens=40, do_sample=True, temperature=0.7, top_p=0.9)
    gen_s = time.time() - t0
    n_new = out.shape[1] - inputs["input_ids"].shape[1]
    reply = tok.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    print(f"[{quant}] load {load_s:.1f}s | {n_new} tokens in {gen_s:.2f}s ({n_new / gen_s:.1f} tok/s)")
    print(f"[{quant}] VRAM allocated {torch.cuda.memory_allocated() / 2**30:.2f} GiB, peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
    print(f"[{quant}] reply: {reply!r}")
    del model
    torch.cuda.empty_cache()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    p.add_argument("--also-4bit", action="store_true")
    args = p.parse_args()
    print(f"torch {torch.__version__} | CUDA {torch.version.cuda} | {torch.cuda.get_device_name(0)}")
    free, total = torch.cuda.mem_get_info()
    print(f"GPU memory free {free / 2**30:.2f} / {total / 2**30:.2f} GiB before loading")
    run(args.model, "bf16")
    if args.also_4bit:
        run(args.model, "4bit")


if __name__ == "__main__":
    main()
