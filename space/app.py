"""Hugging Face Space entry point for the SimuLearn child-model demo (ZeroGPU).

Space settings (set them in the Space's Settings page; never commit them):
  hardware                ZeroGPU (free accounts can't host Gradio Spaces on cpu-basic)
  variable ADAPTER_REPO   e.g. <hf-user>/simulearn-adapters (private model repo with age<N>/ folders)
  secret   HF_TOKEN       read-only token that can see the private adapter repo
  secret   DEMO_PASSWORD  the shared team password
  secret   MONGODB_URI    MongoDB Atlas connection string (optional: without it, nothing is saved)

ZeroGPU lends a GPU only while a @spaces.GPU function runs. `spaces` must be imported before torch, and the
model is moved to cuda at startup (ZeroGPU emulates cuda outside those calls). Off ZeroGPU the decorator does
nothing and the demo falls back to whatever device is available.
"""
import spaces  # noqa: I001  (must come before torch)

import os

from huggingface_hub import snapshot_download

from src.demo.chat_demo import DEFAULT_CONFIG, Demo, build_ui, find_adapters, launch, timed
from src.demo.store import DemoStore
from src.utils.config import load_config, resolve

adapters_dir = snapshot_download(os.environ["ADAPTER_REPO"], token=os.getenv("HF_TOKEN"), local_dir="adapters",
                                 allow_patterns=["age*/adapter_config.json", "age*/adapter_model.safetensors"])
cfg = load_config(resolve(DEFAULT_CONFIG))
demo = Demo(cfg, find_adapters(cfg, adapters_dir), device="cuda" if os.getenv("SPACES_ZERO_GPU") else None)


# One GPU call per turn for both columns, with plain (picklable) arguments at module level, as ZeroGPU requires.
# Each visitor has a small daily GPU quota, and ZeroGPU appears to need `duration` seconds of it left to start a call, so
# keep duration short: two replies of at most 60 tokens take a few seconds on the GPU.
@spaces.GPU(duration=15)
def gpu_reply_both(ft_request, base_request):
    return timed(demo.reply, ft_request), timed(demo.reply, base_request)


launch(build_ui(demo, DemoStore.from_env(), reply_both=gpu_reply_both), port=7860)
