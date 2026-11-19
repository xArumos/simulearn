"""The guard that refuses models from countries of concern (POLICIES.md §1).

Only name strings and fake adapter_config.json files are used: no prohibited model or tokenizer is ever downloaded
or loaded here, and the loader tests replace from_pretrained with a stub that fails the test if it is reached.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from src.utils.config import PROJECT_ROOT
from src.utils.model_policy import ProhibitedModelError, adapter_base_model, check_model, is_denied

DENIED = [
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "qwen/qwen3-8b",
    "deepseek-ai/DeepSeek-V3",
    "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
    "someone/DeepSeek-R1-Distill-Llama-8B",  # distill re-uploaded under another org
    "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit",  # re-quantized re-upload
    "THUDM/chatglm3-6b",
    "zai-org/GLM-4.5",
    "moonshotai/Kimi-K2-Instruct",
    "01-ai/Yi-1.5-9B-Chat",
    "baichuan-inc/Baichuan2-7B-Chat",
    "internlm/internlm2_5-7b-chat",
    "MiniMaxAI/MiniMax-M1-80k",
    "tencent/Hunyuan-7B-Instruct",
    "baidu/ERNIE-4.5-0.3B-PT",
    "ByteDance-Seed/Seed-Coder-8B-Instruct",
    "/models/qwen2.5-1.5b",  # local copy
]
ALLOWED = [
    "meta-llama/Llama-3.2-1B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "google/gemma-2-2b-it",
    "google/gemma-3-4b-it",
    "HuggingFaceTB/SmolLM2-360M-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]


@pytest.mark.parametrize("name", DENIED)
def test_denied_names_are_refused(name):
    assert is_denied(name)
    with pytest.raises(ProhibitedModelError, match="POLICIES.md"):
        check_model(name)


@pytest.mark.parametrize("name", ALLOWED)
def test_allowed_names_pass(name):
    assert not is_denied(name)
    check_model(name)


def test_error_names_the_model():
    with pytest.raises(ProhibitedModelError) as e:
        check_model("deepseek-ai/DeepSeek-R1-Distill-Llama-8B")
    assert "deepseek-ai/DeepSeek-R1-Distill-Llama-8B" in str(e.value)


def _fake_adapter(tmp_path, base: str, dirname: str = "adapter"):
    d = tmp_path / dirname
    d.mkdir()
    (d / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": base, "peft_type": "LORA"}))
    return d


def test_adapter_trained_on_qwen_is_refused_even_with_an_allowed_name(tmp_path):
    adapter = _fake_adapter(tmp_path, "Qwen/Qwen2.5-1.5B-Instruct")
    assert adapter_base_model(adapter) == "Qwen/Qwen2.5-1.5B-Instruct"
    with pytest.raises(ProhibitedModelError, match="Qwen/Qwen2.5-1.5B-Instruct"):
        check_model("meta-llama/Llama-3.2-1B-Instruct", adapter)


def test_adapter_trained_on_llama_passes(tmp_path):
    adapter = _fake_adapter(tmp_path, "meta-llama/Llama-3.2-1B-Instruct")
    check_model("meta-llama/Llama-3.2-1B-Instruct", adapter)
    check_model("meta-llama/Llama-3.2-1B-Instruct", tmp_path / "not_trained_yet")  # no adapter_config.json yet


def test_adapter_path_naming_qwen_is_refused(tmp_path):
    adapter = _fake_adapter(tmp_path, "meta-llama/Llama-3.2-1B-Instruct", dirname="20260101-0000_qwen1.5b_lora_ep1")
    with pytest.raises(ProhibitedModelError):
        check_model("meta-llama/Llama-3.2-1B-Instruct", adapter)


def _forbid_from_pretrained(monkeypatch):
    import src.utils.modeling as modeling

    def boom(*a, **k):
        raise AssertionError("from_pretrained was reached; the guard must run first")

    monkeypatch.setattr(modeling.AutoTokenizer, "from_pretrained", boom)
    monkeypatch.setattr(modeling.AutoModelForCausalLM, "from_pretrained", boom)
    return modeling


def test_loaders_refuse_before_from_pretrained(monkeypatch, tmp_path):
    modeling = _forbid_from_pretrained(monkeypatch)
    with pytest.raises(ProhibitedModelError):
        modeling.load_tokenizer("Qwen/Qwen2.5-1.5B-Instruct")
    with pytest.raises(ProhibitedModelError):
        modeling.load_model({"name": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "device_map": "cpu"})
    adapter = _fake_adapter(tmp_path, "Qwen/Qwen2.5-1.5B-Instruct")
    with pytest.raises(ProhibitedModelError):
        modeling.load_model({"name": "meta-llama/Llama-3.2-1B-Instruct", "device_map": "cpu", "adapter": str(adapter)})


def test_cli_exit_codes(tmp_path):
    def cli(*args):
        return subprocess.run([sys.executable, "-m", "src.utils.model_policy", *args], cwd=PROJECT_ROOT,
                              capture_output=True, text=True, timeout=60)
    assert cli("meta-llama/Llama-3.2-1B-Instruct").returncode == 0
    r = cli("Qwen/Qwen2.5-7B-Instruct", "--context", "configs/x.yaml")
    assert r.returncode == 3 and "POLICIES.md" in r.stderr and "configs/x.yaml" in r.stderr
    r = cli("meta-llama/Llama-3.2-1B-Instruct", "--adapter", str(_fake_adapter(tmp_path, "Qwen/Qwen2.5-7B-Instruct")))
    assert r.returncode == 3


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("run_name", ["qwen1.5b_lora_ep1_hpg", "qwen7b_qlora_smoke_hpg", "qwen1.5b_base-default_hpg"])
def test_submit_all_refuses_qwen_config_before_any_sbatch(run_name):
    env = {**os.environ, "HPG_ENV_FILE": "scripts/slurm/hpg.env.example", "PYTHON": sys.executable}
    r = subprocess.run(["bash", "scripts/slurm/submit_all.sh", "--dry-run", "--only", run_name], cwd=PROJECT_ROOT,
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "sbatch" not in r.stdout and "JOB_" not in r.stdout
    assert "POLICIES.md" in r.stderr and run_name in r.stderr


def test_every_qwen_config_in_the_repo_is_refused():
    """The historical Qwen configs stay in the repo, but each one must fail the guard."""
    import yaml

    qwen = sorted(p for p in (PROJECT_ROOT / "configs").rglob("*.yaml") if "qwen" in p.name)
    assert qwen
    for p in qwen:
        cfg = yaml.safe_load(p.read_text())
        name = (cfg.get("model") or {}).get("name") or cfg.get("base_model")
        assert name and is_denied(name), p
