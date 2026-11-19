"""Desktop test-session helpers (issue #30): scripts/demo_up.sh and scripts/demo_down.sh.

Stub `systemctl`, `docker`, `journalctl` and `nvidia-smi` record their calls and keep unit state in files, and PATH
holds only those stubs plus links to the few system tools the scripts use, so no real service is touched.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from src.utils.config import PROJECT_ROOT

UP = PROJECT_ROOT / "scripts" / "demo_up.sh"
DOWN = PROJECT_ROOT / "scripts" / "demo_down.sh"
UNITS = ("simulearn-demo", "simulearn-tunnel")
TOOLS = ("bash", "cat", "date", "dirname", "grep", "id", "sed", "sleep", "tail", "rm", "touch")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

SYSTEMCTL = r"""#!/bin/bash
echo "systemctl $*" >> "$STUB_STATE/calls.log"
[ "$1" = --user ] && shift
cmd="$1"; shift
case "$cmd" in
  is-active)
    [ "$1" = --quiet ] && shift
    [ -e "$STUB_STATE/active-$1" ] ;;
  start)
    [ -e "$STUB_STATE/start-fails" ] && exit 1
    for u in "$@"; do
      [ -e "$STUB_STATE/never-active-$u" ] || touch "$STUB_STATE/active-$u"
    done ;;
  stop)
    [ -e "$STUB_STATE/stop-fails" ] && exit 1
    for u in "$@"; do rm -f "$STUB_STATE/active-$u"; done ;;
  *) exit 0 ;;
esac
"""

DOCKER = r"""#!/bin/bash
echo "docker $*" >> "$STUB_STATE/calls.log"
[ -e "$STUB_STATE/docker-broken" ] && { echo "permission denied" >&2; exit 1; }
exit 0
"""

JOURNALCTL = r"""#!/bin/bash
echo "journalctl $*" >> "$STUB_STATE/calls.log"
while [ $# -gt 0 ]; do
  [ "$1" = -u ] && { cat "$STUB_STATE/journal-$2" 2>/dev/null; exit 0; }
  shift
done
"""

NVIDIA_SMI = """#!/bin/bash
echo "0, Fake GPU, 321 MiB, 12282 MiB"
"""


@pytest.fixture
def listener():
    """A socket listening on a free 127.0.0.1 port, standing in for the loaded demo."""
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


class Session:
    """An isolated HOME, PATH and stub state for one test."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.unit_dir = self.home / ".config" / "systemd" / "user"
        self.state = tmp_path / "state"
        self.bin = tmp_path / "bin"
        for d in (self.unit_dir, self.state, self.bin):
            d.mkdir(parents=True)
        for tool in TOOLS:
            (self.bin / tool).symlink_to(shutil.which(tool))
        self.stub("systemctl", SYSTEMCTL)
        self.stub("docker", DOCKER)
        self.stub("journalctl", JOURNALCTL)
        self.stub("nvidia-smi", NVIDIA_SMI)
        self.install_units()
        self.dotenv = tmp_path / "dotenv"
        self.dotenv.write_text("DEMO_PASSWORD=hunter2-secret\nMONGODB_URI=mongodb://user:dbsecret@127.0.0.1:27017\n")
        self.config = tmp_path / "config.yml"
        self.config.write_text(
            "tunnel: 0000\ncredentials-file: /home/x/.cloudflared/0000.json\ningress:\n"
            "  - hostname: demo.example.org\n    service: http://127.0.0.1:7860\n"
            "  - service: http_status:404\n")
        self.journal("simulearn-demo", "Demo: ages [5] on cuda\n"
                     "Demo: saving on; serving http://127.0.0.1:7860\n")

    def stub(self, name: str, body: str):
        (self.bin / name).write_text(body)
        (self.bin / name).chmod(0o755)

    def remove(self, name: str):
        (self.bin / name).unlink()

    def install_units(self, named: bool = True):
        mode = "named" if named else "quick"
        for u in UNITS:
            exec_start = f"/bin/bash %h/dev/simulearn/scripts/{'tunnel.sh ' + mode if 'tunnel' in u else 'serve_demo.sh'}"
            (self.unit_dir / f"{u}.service").write_text(f"[Service]\nExecStart={exec_start}\n")

    def journal(self, unit: str, text: str):
        (self.state / f"journal-{unit}").write_text(text)

    def flag(self, name: str):
        (self.state / name).touch()

    def active(self, unit: str) -> bool:
        return (self.state / f"active-{unit}").exists()

    def calls(self) -> list[str]:
        log = self.state / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def run(self, script: Path, *args: str, **env: str):
        full_env = {"PATH": str(self.bin), "HOME": str(self.home), "STUB_STATE": str(self.state),
                    "SIMULEARN_ENV_FILE": str(self.dotenv), "TUNNEL_CONFIG": str(self.config),
                    "DEMO_UP_TUNNEL_WAIT_SECONDS": "1", "LANG": "C.UTF-8", **env}
        out = subprocess.run([shutil.which("bash"), str(script), *args], env=full_env, capture_output=True,
                             text=True, timeout=60, cwd=self.tmp)
        assert "hunter2-secret" not in out.stdout + out.stderr
        assert "dbsecret" not in out.stdout + out.stderr
        return out


@pytest.fixture
def s(tmp_path) -> Session:
    return Session(tmp_path)


# --- demo_up.sh: success --------------------------------------------------------------------------------------------

def test_up_starts_db_then_units_and_prints_url_and_saving(s, listener):
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    calls = s.calls()
    up = calls.index("docker compose up -d")
    start = next(i for i, c in enumerate(calls) if c.startswith("systemctl --user start"))
    assert up < start and "simulearn-tunnel" in calls[start]
    assert s.active("simulearn-tunnel") and s.active("simulearn-demo")
    assert "Public URL: https://demo.example.org" in out.stdout
    assert "Demo: saving on" in out.stdout


def test_up_prints_every_hostname_from_the_config(s, listener):
    s.config.write_text(
        "ingress:\n  - hostname: demo.example.org\n    service: http://127.0.0.1:7860\n"
        "  - hostname: \"app.example.org\"\n    service: http://127.0.0.1:8000\n  - service: http_status:404\n")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert "Public URL: https://demo.example.org" in out.stdout
    assert "Public URL: https://app.example.org" in out.stdout


def test_up_url_is_not_hard_coded(s, listener):
    s.config.write_text("ingress:\n  - hostname: other.test\n    service: x\n  - service: http_status:404\n")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert "https://other.test" in out.stdout and "example.org" not in out.stdout


def test_up_reports_saving_off(s, listener):
    s.journal("simulearn-demo", "Demo: saving OFF (MONGODB_URI empty or MongoDB unreachable); serving http://x\n")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert "Demo: saving OFF (MONGODB_URI empty or MongoDB unreachable)" in out.stdout


def test_up_quick_mode_reads_the_url_from_the_journal(s, listener):
    s.install_units(named=False)
    s.journal("simulearn-tunnel", "INF |  https://three-random-words.trycloudflare.com  |\n")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert "Public URL: https://three-random-words.trycloudflare.com" in out.stdout


def test_up_no_db_skips_docker_entirely(s, listener):
    s.remove("docker")  # not even needed
    out = s.run(UP, "--no-db", DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert not any(c.startswith("docker") for c in s.calls())
    assert s.active("simulearn-demo")


def test_up_twice_is_fine(s, listener):
    assert s.run(UP, DEMO_PORT=str(listener)).returncode == 0
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert "Public URL: https://demo.example.org" in out.stdout


def test_up_password_from_shell_counts(s, listener):
    s.dotenv.unlink()
    out = s.run(UP, DEMO_PORT=str(listener), DEMO_PASSWORD="x")
    assert out.returncode == 0, out.stderr


# --- demo_up.sh: failures -------------------------------------------------------------------------------------------

def assert_nothing_started(s: Session):
    assert not any(c.startswith(("systemctl --user start", "docker compose up")) for c in s.calls())


@pytest.mark.parametrize("unit", UNITS)
def test_up_refuses_when_a_unit_is_not_installed(s, listener, unit):
    (s.unit_dir / f"{unit}.service").unlink()
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode != 0
    assert f"{unit}.service is not installed" in out.stderr
    assert_nothing_started(s)


@pytest.mark.parametrize("dotenv,env", [
    (None, {}),
    ("DEMO_PASSWORD=\n", {}),
    ('DEMO_PASSWORD=""\n', {}),
    ("DEMO_PASSWORD=secret\n", {"DEMO_PASSWORD": ""}),  # shell wins over .env, like tunnel.sh
])
def test_up_refuses_without_a_password(s, listener, dotenv, env):
    s.dotenv.unlink()
    if dotenv is not None:
        s.dotenv.write_text(dotenv)
    out = s.run(UP, DEMO_PORT=str(listener), **env)
    assert out.returncode != 0
    assert "DEMO_PASSWORD is empty" in out.stderr
    assert_nothing_started(s)


def test_up_refuses_when_docker_is_missing(s, listener):
    s.remove("docker")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode != 0
    assert "docker is not on PATH" in out.stderr and "--no-db" in out.stderr
    assert_nothing_started(s)


def test_up_refuses_when_docker_is_not_usable(s, listener):
    s.flag("docker-broken")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode != 0
    assert "'docker' group" in out.stderr and "reopen the terminal" in out.stderr
    assert_nothing_started(s)


def test_up_times_out_when_the_demo_never_listens(s):
    out = s.run(UP, DEMO_PORT=str(free_port()), DEMO_UP_WAIT_SECONDS="1")
    assert out.returncode != 0
    assert "after 1 s" in out.stderr and "journalctl --user -u simulearn-demo" in out.stderr


def test_up_fails_when_the_tunnel_unit_does_not_come_up(s, listener):
    s.flag("never-active-simulearn-tunnel")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode != 0
    assert "simulearn-tunnel is not active" in out.stderr


def test_up_fails_when_the_port_belongs_to_something_else(s, listener):
    s.flag("never-active-simulearn-demo")
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode != 0
    assert "simulearn-demo is not running" in out.stderr


def test_up_refuses_while_the_product_runs(s, listener):
    s.flag("active-simulearn-product")  # issue #63: one GPU app at a time
    out = s.run(UP, DEMO_PORT=str(listener))
    assert out.returncode != 0 and "product_down.sh --keep-db" in out.stderr
    assert_nothing_started(s)


def test_up_rejects_unknown_flags(s, listener):
    out = s.run(UP, "--keep-db", DEMO_PORT=str(listener))
    assert out.returncode != 0 and "usage" in out.stderr
    assert_nothing_started(s)


# --- demo_down.sh ---------------------------------------------------------------------------------------------------

def test_down_stops_both_units_by_name_then_the_db_and_shows_gpu(s):
    s.flag("active-simulearn-demo")
    s.flag("active-simulearn-tunnel")
    out = s.run(DOWN)
    assert out.returncode == 0, out.stderr
    calls = s.calls()
    assert "systemctl --user stop simulearn-tunnel" in calls
    assert "systemctl --user stop simulearn-demo" in calls
    assert calls.index("systemctl --user stop simulearn-demo") < calls.index("docker compose stop")
    assert not s.active("simulearn-demo") and not s.active("simulearn-tunnel")
    assert "321 MiB" in out.stdout


def test_down_keep_db_leaves_mongo_alone(s):
    out = s.run(DOWN, "--keep-db")
    assert out.returncode == 0, out.stderr
    assert "docker compose stop" not in s.calls()
    assert "systemctl --user stop simulearn-demo" in s.calls()


def test_down_twice_is_fine(s):
    assert s.run(DOWN).returncode == 0
    out = s.run(DOWN)
    assert out.returncode == 0, out.stderr


def test_down_without_nvidia_smi_still_works(s):
    s.remove("nvidia-smi")
    out = s.run(DOWN)
    assert out.returncode == 0, out.stderr
    assert "nvidia-smi not found" in out.stdout


def test_down_fails_loudly_when_the_demo_cannot_be_stopped(s):
    s.flag("active-simulearn-demo")
    s.flag("stop-fails")
    out = s.run(DOWN)
    assert out.returncode != 0
    assert "VRAM" in out.stderr


def test_down_reports_unusable_docker(s):
    s.flag("docker-broken")
    out = s.run(DOWN)
    assert out.returncode != 0
    assert "MongoDB was not stopped" in out.stderr
    assert "systemctl --user stop simulearn-demo" in s.calls()  # the GPU is still freed


def test_down_rejects_unknown_flags(s):
    out = s.run(DOWN, "--no-db")
    assert out.returncode != 0 and "usage" in out.stderr
    assert s.calls() == []


def test_script_syntax():
    for script in (UP, DOWN, PROJECT_ROOT / "scripts" / "_demo_env.sh"):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
