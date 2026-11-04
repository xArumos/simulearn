#!/usr/bin/env bash
# Upload the demo's LoRA adapters (configs/demo.yaml) to a PRIVATE Hugging Face model repo as age<N>/.
# Only adapter_config.json + adapter_model.safetensors go up: no data, no samples, no model card.
# Log in yourself first:  hf auth login
# Usage (inside WSL): bash scripts/upload_adapters.sh <hf-user>/simulearn-adapters
set -euo pipefail
source "$(dirname "$0")/env_wsl.sh"
REPO="${1:?usage: upload_adapters.sh <hf-user>/simulearn-adapters}"
python - "$REPO" <<'PY'
import subprocess, sys
from src.demo.chat_demo import DEFAULT_CONFIG, find_adapters
from src.utils.config import load_config, resolve

repo = sys.argv[1]
adapters = find_adapters(load_config(resolve(DEFAULT_CONFIG)))
for age, a in adapters.items():
    print(f"age{age}: {a['path']}")
    subprocess.run(["hf", "upload", repo, str(a["path"]), f"age{age}", "--repo-type", "model", "--private",
                    "--include", "adapter_*",  # adapter_config.json + adapter_model.safetensors
                    "--commit-message", f"age{age} adapter: {a['path'].parent.name}"], check=True)
print(f"Uploaded ages {sorted(adapters)} to {repo} (private).")
PY
