"""Hugging Face Space entry point for the SimuLearn child-model demo (CPU).

Space settings (set them in the Space's Settings page; never commit them):
  variable ADAPTER_REPO   e.g. <hf-user>/simulearn-adapters (private model repo with age<N>/ folders)
  secret   HF_TOKEN       read-only token that can see the private adapter repo
  secret   DEMO_PASSWORD  the shared team password
  secret   MONGODB_URI    MongoDB Atlas connection string (optional: without it, nothing is saved)
"""
import os

from huggingface_hub import snapshot_download

from src.demo.chat_demo import DEFAULT_CONFIG, Demo, build_ui, find_adapters, launch
from src.demo.store import DemoStore
from src.utils.config import load_config, resolve

adapters_dir = snapshot_download(os.environ["ADAPTER_REPO"], token=os.getenv("HF_TOKEN"), local_dir="adapters",
                                 allow_patterns=["age*/adapter_config.json", "age*/adapter_model.safetensors"])
cfg = load_config(resolve(DEFAULT_CONFIG))
demo = Demo(cfg, find_adapters(cfg, adapters_dir))
launch(build_ui(demo, DemoStore.from_env()), port=7860)
