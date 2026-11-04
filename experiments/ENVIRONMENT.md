# Environment

_Recorded 2026-10-15._

## Hardware
- GPU: NVIDIA GeForce RTX 4070 Ti, **12 GB VRAM** (12282 MiB). Windows driver 616.56 (CUDA 13.4 driver API).
- CPU: AMD Ryzen 7 7800X3D (8 cores / 16 threads). Host RAM 31 GB; WSL2 sees ~15 GB by default.
- About 1.2 GB VRAM is used by Windows desktop apps (WSL reported 10.78 / 11.99 GiB free). Close OBS, Wallpaper Engine, game launchers, etc. before big runs.

## Software
- Host: Windows 11 Pro 10.0.26200.
- Training runs in **WSL2, Ubuntu 26.04.1 LTS**, kernel 6.18.54.1-microsoft-standard-WSL2.
- Python **3.12.15** (uv-managed), venv at `~/venvs/simulearn` (Linux filesystem).
- uv 0.13.1 at `~/.local/bin/uv`.
- Hugging Face cache: `~/.cache/huggingface` (Linux filesystem).
- Code lives on the Windows drive at `C:\Users\justin\dev\simulearn-testing` (`/mnt/c/...` inside WSL).

Key packages (full list in `requirements.txt`):

| Package | Version |
|---|---|
| torch | 2.14.1+cu132 (CUDA 13.2) |
| transformers | 5.20.0 |
| peft | 0.21.2 |
| trl | 1.16.0 |
| datasets | 5.1.0 |
| accelerate | 1.15.0 |
| bitsandbytes | 0.50.2 |
| pylangacq | 0.23.0 |
| numpy / pandas / scipy | 2.5.4 / 3.0.6 / 1.18.1 |

No flash-attn. Attention uses PyTorch SDPA (the default).

## How to get a shell in this environment
```bash
wsl -d Ubuntu
source /mnt/c/Users/justin/dev/simulearn-testing/scripts/env_wsl.sh
```

## GPU smoke test (`scripts/gpu_smoke_test.py`, Qwen/Qwen2.5-1.5B-Instruct)
| Mode | VRAM peak | Speed (40 tokens) | Note |
|---|---|---|---|
| bf16 | 2.89 GiB | 28.7 tok/s | Load time includes first download |
| 4-bit NF4 (bitsandbytes) | 1.11 GiB | 40.6 tok/s | Confirms QLoRA tooling works |

Sample bf16 reply to "What did you do at school today?" with the child system prompt: long, fluent, adult-sounding ("We learned about different animals and how they live in the jungle..."). This is the failure mode fine-tuning should fix.
