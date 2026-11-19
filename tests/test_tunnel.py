"""Cloudflare Tunnel for the desktop demo (issue #15): scripts/tunnel.sh, the example config and the systemd unit.

A stub `cloudflared` on PATH records its arguments, so no real tunnel is opened. The missing-cloudflared test
runs with a PATH holding only the tools tunnel.sh needs, so an installed cloudflared can never be found.
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


def run_tunnel(tmp_path: Path, *args: str, env_file: str | None = None, **env: str):
    """Run tunnel.sh with a stub cloudflared (prints its args) and an isolated .env."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
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


# External commands tunnel.sh and scripts/_demo_env.sh run; everything else they use is a bash builtin.
TUNNEL_TOOLS = ("bash", "dirname", "grep", "tail", "sed", "sleep")


def tools_only_dir(tmp_path: Path) -> Path:
    """A directory of symlinks to just TUNNEL_TOOLS, so a PATH of only this directory cannot find cloudflared."""
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    for tool in TUNNEL_TOOLS:
        real = shutil.which(tool)
        assert real is not None, f"{tool} is needed to run tunnel.sh"
        (bin_dir / tool).symlink_to(real)
    return bin_dir


def test_missing_cloudflared_points_at_the_readme(tmp_path, listener):
    # Runs even where cloudflared is installed: PATH holds only the tools tunnel.sh needs, so a real cloudflared
    # (in /usr/bin, /usr/local/bin, ~/.local/bin, ...) can never be found or started.
    bin_dir = tools_only_dir(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DEMO_", "TUNNEL_"))}
    env.update({"PATH": str(bin_dir), "SIMULEARN_ENV_FILE": str(tmp_path / "dotenv"),
                "DEMO_PASSWORD": "x", "DEMO_PORT": str(listener)})
    assert shutil.which("cloudflared", path=env["PATH"]) is None
    out = subprocess.run([str(bin_dir / "bash"), str(TUNNEL)], env=env, capture_output=True, text=True,
                         timeout=10, cwd=tmp_path)
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


def named_config(tmp_path: Path, *routes: tuple[str, int]) -> Path:
    """A config.yml with one ingress rule per (hostname, port), then the 404 catch-all."""
    cfg = tmp_path / "config.yml"
    rules = "".join(f"  - hostname: {h}\n    service: http://127.0.0.1:{p}\n" for h, p in routes)
    cfg.write_text(f"tunnel: simulearn-demo\ningress:\n{rules}  - service: http_status:404\n")
    return cfg


def test_named_mode_runs_the_configured_tunnel(tmp_path, listener):
    cfg = named_config(tmp_path, ("demo.example.org", listener))
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(listener), TUNNEL_CONFIG=str(cfg))
    assert out.returncode == 0, out.stderr
    args = cloudflared_args(out)
    assert args[0] == "tunnel"
    assert args[args.index("--config") + 1] == str(cfg)
    assert args[-1] == "run"
    assert "--url" not in args


# Issue #63: one tunnel, two hostnames (demo + product). Each app can run alone.

def test_named_mode_warns_when_the_demo_is_down_but_the_product_is_up(tmp_path, listener):
    demo = free_port()
    cfg = named_config(tmp_path, ("demo.example.org", demo), ("app.example.org", listener))
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(demo), TUNNEL_CONFIG=str(cfg))
    assert out.returncode == 0, out.stderr
    assert cloudflared_args(out)[-1] == "run"
    assert "WARNING" in out.stderr and f"127.0.0.1:{demo}" in out.stderr and "demo.example.org" in out.stderr
    assert f"app.example.org -> http://127.0.0.1:{listener} (up)" in out.stderr


def test_named_mode_warns_when_the_product_is_down_but_the_demo_is_up(tmp_path, listener):
    product = free_port()
    cfg = named_config(tmp_path, ("demo.example.org", listener), ("app.example.org", product))
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(listener), TUNNEL_CONFIG=str(cfg))
    assert out.returncode == 0, out.stderr
    assert "WARNING" in out.stderr and "app.example.org" in out.stderr
    assert cloudflared_args(out)[-1] == "run"


def test_named_mode_refuses_when_every_backend_is_down(tmp_path):
    demo, product = free_port(), free_port()
    cfg = named_config(tmp_path, ("demo.example.org", demo), ("app.example.org", product))
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(demo), TUNNEL_CONFIG=str(cfg))
    assert out.returncode != 0
    assert "nothing is listening on any port" in out.stderr and str(product) in out.stderr
    assert cloudflared_args(out) == []


def test_named_mode_without_a_demo_route_needs_no_demo_password(tmp_path, listener):
    cfg = named_config(tmp_path, ("app.example.org", listener))
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="", DEMO_PORT=str(free_port()), TUNNEL_CONFIG=str(cfg))
    assert out.returncode == 0, out.stderr


def test_named_mode_with_a_demo_route_still_needs_the_password(tmp_path, listener):
    demo = free_port()
    cfg = named_config(tmp_path, ("demo.example.org", demo), ("app.example.org", listener))
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="", DEMO_PORT=str(demo), TUNNEL_CONFIG=str(cfg))
    assert out.returncode != 0 and "DEMO_PASSWORD" in out.stderr
    assert cloudflared_args(out) == []


def test_named_mode_refuses_a_config_without_local_services(tmp_path, listener):
    cfg = tmp_path / "config.yml"
    cfg.write_text("tunnel: simulearn-demo\ningress:\n  - service: http_status:404\n")
    out = run_tunnel(tmp_path, "named", DEMO_PASSWORD="x", DEMO_PORT=str(listener), TUNNEL_CONFIG=str(cfg))
    assert out.returncode != 0 and "no ingress rule" in out.stderr
    assert cloudflared_args(out) == []


def test_ingress_routes_parses_hostnames_quotes_comments_and_catch_alls(tmp_path):
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        "tunnel: x\ningress:\n  # a comment\n  - hostname: demo.example.org\n    service: http://127.0.0.1:7860\n"
        "  - hostname: \"app.example.org\"   # product\n    service: 'http://localhost:8000'\n"
        "  - service: http://127.0.0.1:9000\n  - service: http_status:404\n")
    helper = PROJECT_ROOT / "scripts" / "_demo_env.sh"
    out = subprocess.run(["bash", "-c", f'. "{helper}"; ingress_routes "{cfg}"'], capture_output=True, text=True)
    assert out.stdout.splitlines() == ["demo.example.org 7860", "app.example.org 8000", "* 9000"]


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
    assert "service: http://127.0.0.1:8000" in text  # the product (issue #63)
    assert text.index("127.0.0.1:8000") < text.index("http_status:404")  # above the catch-all
    assert "http_status:404" in text  # catch-all rule cloudflared requires
    assert "arumos" not in text  # generic placeholder hostnames only
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


def test_unit_follows_the_apps_but_does_not_start_them():
    keys = unit_keys()
    assert any("scripts/tunnel.sh" in v for v in keys["ExecStart"])
    assert "simulearn-demo.service" in " ".join(keys["After"])
    assert "simulearn-product.service" in " ".join(keys["After"])
    # Starting the tunnel for the product must not load the demo onto the GPU too (issue #63).
    for key in ("Wants", "Requires", "BindsTo"):
        assert "simulearn-demo" not in " ".join(keys.get(key, []))
    assert keys["Restart"] == ["on-failure"]
    assert keys["WantedBy"] == ["default.target"]
    assert any(v.startswith("TUNNEL_WAIT_SECONDS=") for v in keys.get("Environment", []))


def test_unit_carries_no_secrets():
    text = UNIT.read_text()
    for secret in ("DEMO_PASSWORD=", "TUNNEL_TOKEN", "--token"):
        assert secret not in text
