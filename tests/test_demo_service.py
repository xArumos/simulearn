"""Desktop demo service (issue #14): serve_demo.sh, the systemd user unit, and the demo's host/device/password options."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from src.demo import chat_demo
from src.utils.config import PROJECT_ROOT

SERVE = PROJECT_ROOT / "scripts" / "serve_demo.sh"
UNIT = PROJECT_ROOT / "scripts" / "systemd" / "simulearn-demo.service"


# --- chat_demo options -------------------------------------------------------------------------------------------

def test_defaults_keep_the_old_local_demo_behaviour():
    a = chat_demo.parse_args([])
    assert (a.host, a.port, a.device, a.require_password) == ("0.0.0.0", 7860, "auto", False)


def test_service_options_parse():
    a = chat_demo.parse_args(["--host", "127.0.0.1", "--device", "cpu", "--require-password"])
    assert (a.host, a.device, a.require_password) == ("127.0.0.1", "cpu", True)


@pytest.mark.parametrize("choice,cuda,expected", [
    ("auto", True, "cuda"), ("auto", False, "cpu"), ("cpu", True, "cpu"), ("cuda", True, "cuda"),
])
def test_pick_device(monkeypatch, choice, cuda, expected):
    monkeypatch.setattr(chat_demo.torch.cuda, "is_available", lambda: cuda)
    assert chat_demo.pick_device(choice) == expected


def test_asking_for_cuda_without_a_gpu_fails_clearly(monkeypatch):
    monkeypatch.setattr(chat_demo.torch.cuda, "is_available", lambda: False)
    with pytest.raises(SystemExit, match="no CUDA GPU"):
        chat_demo.pick_device("cuda")


def test_require_password(monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="DEMO_PASSWORD"):
        chat_demo.check_password(required=True)
    monkeypatch.setenv("DEMO_PASSWORD", "")
    with pytest.raises(SystemExit, match="DEMO_PASSWORD"):
        chat_demo.check_password(required=True)
    chat_demo.check_password(required=False)  # the plain local demo may run without one
    monkeypatch.setenv("DEMO_PASSWORD", "x")
    chat_demo.check_password(required=True)


def test_launch_binds_the_requested_host(monkeypatch):
    seen = {}

    class FakeUI:
        def launch(self, **kw):
            seen.update(kw)

    monkeypatch.setenv("DEMO_PASSWORD", "x")
    chat_demo.launch(FakeUI(), 7861, host="127.0.0.1")
    assert seen["server_name"] == "127.0.0.1" and seen["server_port"] == 7861
    assert seen["auth"]("anyone", "x") and not seen["auth"]("anyone", "y")


# --- serve_demo.sh -----------------------------------------------------------------------------------------------

def run_serve(tmp_path: Path, *args: str, **env: str) -> list[str]:
    """Run serve_demo.sh with a fake `python` that prints its arguments instead of starting the demo."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "python").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$PWD" "$@"\n')
    (fake / "python").chmod(0o755)
    full_env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "SIMULEARN_VENV": str(tmp_path / "no-venv"), **env}
    for key in ("DEMO_HOST", "DEMO_PORT", "DEMO_DEVICE"):
        if key not in env:
            full_env.pop(key, None)
    out = subprocess.run(["bash", str(SERVE), *args], env=full_env, capture_output=True, text=True, timeout=30, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    return out.stdout.splitlines()


pytestmark_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytestmark_bash
def test_serve_script_binds_localhost_and_requires_a_password(tmp_path):
    cwd, *argv = run_serve(tmp_path)
    assert Path(cwd) == PROJECT_ROOT  # runs from the repo, so configs/demo.yaml and experiments/ resolve
    assert argv[:2] == ["-m", "src.demo.chat_demo"]
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--port") + 1] == "7860"
    assert argv[argv.index("--device") + 1] == "auto"
    assert "--require-password" in argv
    assert argv[argv.index("--config") + 1] == "configs/demo.yaml"


@pytestmark_bash
def test_serve_script_settings_come_from_the_environment_and_extra_args_pass_through(tmp_path):
    _, *argv = run_serve(tmp_path, "--selftest", DEMO_PORT="7999", DEMO_DEVICE="cpu")
    assert argv[argv.index("--port") + 1] == "7999"
    assert argv[argv.index("--device") + 1] == "cpu"
    assert argv[-1] == "--selftest"


@pytestmark_bash
def test_serve_script_syntax():
    assert subprocess.run(["bash", "-n", str(SERVE)]).returncode == 0


# --- systemd unit ------------------------------------------------------------------------------------------------

def unit_keys() -> dict[str, str]:
    keys = {}
    for line in UNIT.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith(("#", ";")):
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    return keys


def test_unit_runs_the_serve_script_and_restarts_on_failure():
    keys = unit_keys()
    assert "scripts/serve_demo.sh" in keys["ExecStart"]
    assert keys["Restart"] == "on-failure"
    assert keys["WantedBy"] == "default.target"  # a user unit, not a system one


def test_unit_carries_no_secrets():
    text = UNIT.read_text()
    for secret in ("DEMO_PASSWORD", "MONGODB_URI", "HF_TOKEN"):
        assert f"{secret}=" not in text  # they live in the git-ignored .env, read by the demo
