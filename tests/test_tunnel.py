"""Cloudflare Tunnel for the desktop demo (issue #15): scripts/tunnel.sh, the example config and the systemd unit.

A stub `cloudflared` on PATH records its arguments, so no real tunnel is opened.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from src.utils.config import PROJECT_ROOT

TUNNEL = PROJECT_ROOT / "scripts" / "tunnel.sh"
EXAMPLE = PROJECT_ROOT / "scripts" / "cloudflared" / "config.yml.example"
UNIT = PROJECT_ROOT / "scripts" / "systemd" / "simulearn-tunnel.service"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def listener():
    """A socket listening on a free 127.0.0.1 port, standing in for the running demo."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(8)
    yield s.getsockname()[1]
    s.close()


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_tunnel(tmp_path: Path, *args: str, stub: bool = True, env_file: str | None = None, **env: str):
    """Run tunnel.sh with a stub cloudflared (prints its args) and an isolated .env."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if stub:
        (bin_dir / "cloudflared").write_text('#!/usr/bin/env bash\nprintf "ARG:%s\\n" "$@"\n')
        (bin_dir / "cloudflared").chmod(0o755)
    dotenv = tmp_path / "dotenv"
    if env_file is not None:
        dotenv.write_text(env_file)
    # Keep only the system tools; drop any real cloudflared that might be on the user's PATH.
    path = f"{bin_dir}:/usr/bin:/bin"
    full_env = {k: v for k, v in os.environ.items() if not k.startswith(("DEMO_", "TUNNEL_"))}
    full_env.update({"PATH": path, "SIMULEARN_ENV_FILE": str(dotenv), **env})
    return subprocess.run(["bash", str(TUNNEL), *args], env=full_env, capture_output=True, text=True,
                          timeout=30, cwd=tmp_path)


def cloudflared_args(out) -> list[str]:
    return [line[4:] for line in out.stdout.splitlines() if line.startswith("ARG:")]


# --- quick mode --------------------------------------------------------------------------------------------------

def test_quick_mode_points_cloudflared_at_the_local_demo(tmp_path, listener):
    out = run_tunnel(tmp_path, DEMO_PASSWORD="x", DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    args = cloudflared_args(out)
    assert args[0] == "tunnel"
    assert args[args.index("--url") + 1] == f"http://127.0.0.1:{listener}"
    assert "--no-autoupdate" in args
    assert "trycloudflare.com" in out.stderr  # tells the user where the URL shows up


def test_quick_is_the_default_and_can_be_named(tmp_path, listener):
    a = run_tunnel(tmp_path, DEMO_PASSWORD="x", DEMO_PORT=str(listener))
    b = run_tunnel(tmp_path, "quick", DEMO_PASSWORD="x", DEMO_PORT=str(listener))
    assert cloudflared_args(a) == cloudflared_args(b)


def test_password_from_dotenv_counts(tmp_path, listener):
    out = run_tunnel(tmp_path, env_file="DEMO_PASSWORD=secret\n", DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert "secret" not in out.stdout + out.stderr  # never echoed


@pytest.mark.parametrize("env_file,env", [
    (None, {}),                                    # nothing anywhere
    ("DEMO_PASSWORD=\n", {}),                      # the .env.example default
    ('DEMO_PASSWORD=""\n', {}),                    # quoted empty
    ("# DEMO_PASSWORD=old\n", {}),                 # commented out
    ("DEMO_PASSWORD=secret\n", {"DEMO_PASSWORD": ""}),  # shell wins over .env, like backend/app/env.py
])
def test_refuses_without_a_password(tmp_path, listener, env_file, env):
    out = run_tunnel(tmp_path, env_file=env_file, DEMO_PORT=str(listener), **env)
    assert out.returncode != 0
    assert "DEMO_PASSWORD" in out.stderr
    assert cloudflared_args(out) == []


def test_refuses_when_nothing_listens(tmp_path):
    out = run_tunnel(tmp_path, DEMO_PASSWORD="x", DEMO_PORT=str(free_port()))
    assert out.returncode != 0
    assert "nothing is listening" in out.stderr
    assert cloudflared_args(out) == []


def test_waits_for_the_demo_when_asked(tmp_path):
    port = free_port()
    out = run_tunnel(tmp_path, DEMO_PASSWORD="x", DEMO_PORT=str(port), TUNNEL_WAIT_SECONDS="1")
    assert out.returncode != 0 and "after waiting 1 s" in out.stderr


def test_missing_cloudflared_points_at_the_readme(tmp_path, listener):
    out = run_tunnel(tmp_path, stub=False, DEMO_PASSWORD="x", DEMO_PORT=str(listener))
    assert out.returncode != 0
    assert "cloudflared" in out.stderr and "README" in out.stderr


def test_unknown_mode_is_rejected(tmp_path, listener):
    out = run_tunnel(tmp_path, "public", DEMO_PASSWORD="x", DEMO_PORT=str(listener))
    assert out.returncode != 0 and "usage" in out.stderr.lower()
    assert cloudflared_args(out) == []


# --- named mode --------------------------------------------------------------------------------------------------

def test_named_mode_refuses_a_missing_config(tmp_path, listener):
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(listener),
                     TUNNEL_CONFIG=str(tmp_path / "nope.yml"))
    assert out.returncode != 0
    assert "config.yml.example" in out.stderr
    assert cloudflared_args(out) == []


def test_named_mode_runs_the_configured_tunnel(tmp_path, listener):
    cfg = tmp_path / "config.yml"
    cfg.write_text("tunnel: simulearn-demo\n")
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(listener), TUNNEL_CONFIG=str(cfg))
    assert out.returncode == 0, out.stderr
    args = cloudflared_args(out)
    assert args[0] == "tunnel"
    assert args[args.index("--config") + 1] == str(cfg)
    assert args[-1] == "run"
    assert "--url" not in args


def test_named_mode_default_config_path_is_the_git_ignored_one(tmp_path, listener):
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(listener))
    if (PROJECT_ROOT / "scripts" / "cloudflared" / "config.yml").exists():
        pytest.skip("a real config exists on this machine")
    assert out.returncode != 0 and "scripts/cloudflared/config.yml" in out.stderr


def test_tunnel_script_syntax():
    assert subprocess.run(["bash", "-n", str(TUNNEL)]).returncode == 0


# --- committed files carry no secrets ----------------------------------------------------------------------------

def test_example_config_targets_the_local_demo_and_keeps_credentials_outside_the_repo():
    text = EXAMPLE.read_text()
    assert "service: http://127.0.0.1:7860" in text
    assert "http_status:404" in text  # catch-all rule cloudflared requires
    cred = next(line for line in text.splitlines() if line.startswith("credentials-file:"))
    assert "~/.cloudflared/" in cred or "/home/" in cred
    assert "<TUNNEL-ID>" in text  # placeholder, not a real tunnel UUID


def test_real_config_and_credentials_are_git_ignored():
    for path in ("scripts/cloudflared/config.yml", "scripts/cloudflared/0000-tunnel.json",
                 "scripts/cloudflared/cert.pem"):
        r = subprocess.run(["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT)
        assert r.returncode == 0, f"{path} is not git-ignored"
    r = subprocess.run(["git", "check-ignore", "-q", "scripts/cloudflared/config.yml.example"], cwd=PROJECT_ROOT)
    assert r.returncode != 0


def unit_keys() -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for line in UNIT.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith(("#", ";")):
            k, v = line.split("=", 1)
            keys.setdefault(k.strip(), []).append(v.strip())
    return keys


def test_unit_follows_the_demo_unit():
    keys = unit_keys()
    assert any("scripts/tunnel.sh" in v for v in keys["ExecStart"])
    assert "simulearn-demo.service" in " ".join(keys["After"])
    assert "simulearn-demo.service" in " ".join(keys["Wants"])
    assert keys["Restart"] == ["on-failure"]
    assert keys["WantedBy"] == ["default.target"]
    assert any(v.startswith("TUNNEL_WAIT_SECONDS=") for v in keys.get("Environment", []))


def test_unit_carries_no_secrets():
    text = UNIT.read_text()
    for secret in ("DEMO_PASSWORD=", "TUNNEL_TOKEN", "--token"):
        assert secret not in text
