"""Serving the educator product on the desktop (issue #63): serve_product.sh, product_up.sh / product_down.sh,
the systemd unit and `create_user.py has-admin`.

Same pattern as tests/test_demo_service.py and tests/test_demo_scripts.py: stub `python`, `systemctl`, `docker`,
`journalctl` and `nvidia-smi` record their calls, and PATH holds only those stubs plus links to the system tools the
scripts use, so no real server, MongoDB, tunnel or GPU is touched.
"""
from __future__ import annotations

import importlib.util
import shutil
import socket
import subprocess
from pathlib import Path

import mongomock
import pytest

from src.product.auth import Auth
from src.utils.config import PROJECT_ROOT
from tests.test_demo_scripts import DOCKER, JOURNALCTL, NVIDIA_SMI, SYSTEMCTL

SERVE = PROJECT_ROOT / "scripts" / "serve_product.sh"
UP = PROJECT_ROOT / "scripts" / "product_up.sh"
DOWN = PROJECT_ROOT / "scripts" / "product_down.sh"
UNIT = PROJECT_ROOT / "scripts" / "systemd" / "simulearn-product.service"
TOOLS = ("bash", "cat", "date", "dirname", "grep", "id", "sed", "sleep", "tail", "rm", "touch")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

# `python scripts/create_user.py has-admin` exits with the code in $STUB_STATE/admin (0 = an active admin exists);
# any other call prints the working directory and its arguments instead of starting the server.
PYTHON = r"""#!/bin/bash
echo "python $*" >> "$STUB_STATE/calls.log"
if [ "$1" = scripts/create_user.py ]; then exit "$(cat "$STUB_STATE/admin" 2>/dev/null || echo 0)"; fi
printf '%s\n' "$PWD" "$@"
"""


@pytest.fixture
def listener():
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


class Box:
    """An isolated HOME, PATH, stub state, .env, frontend build and tunnel config for one test."""

    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.unit_dir = self.home / ".config" / "systemd" / "user"
        self.state = tmp_path / "state"
        self.bin = tmp_path / "bin"
        self.dist = tmp_path / "dist"
        for d in (self.unit_dir, self.state, self.bin, self.dist):
            d.mkdir(parents=True)
        (self.dist / "index.html").write_text("<!doctype html>")
        for tool in TOOLS:
            (self.bin / tool).symlink_to(shutil.which(tool))
        for name, body in (("systemctl", SYSTEMCTL), ("docker", DOCKER), ("journalctl", JOURNALCTL),
                           ("nvidia-smi", NVIDIA_SMI), ("python", PYTHON)):
            self.stub(name, body)
        self.install_units()
        self.dotenv = tmp_path / "dotenv"
        self.dotenv.write_text("DEMO_PASSWORD=hunter2-secret\nMONGODB_URI=mongodb://user:dbsecret@127.0.0.1:27017\n")
        self.config = tmp_path / "config.yml"
        # The demo is off: a bound, non-listening socket holds its port, so connections are refused and no other
        # test socket (e.g. the `listener` fixture) can be handed the same port.
        self._demo_socket = socket.socket()
        self._demo_socket.bind(("127.0.0.1", 0))
        self.demo_port = self._demo_socket.getsockname()[1]
        self.journal("simulearn-product", "SimuLearn: base with ages [5] on cuda\n"
                     "SimuLearn: saving on; frontend served from frontend/dist; http://127.0.0.1:8000\n")

    def stub(self, name: str, body: str):
        (self.bin / name).write_text(body)
        (self.bin / name).chmod(0o755)

    def remove(self, name: str):
        (self.bin / name).unlink()

    def install_units(self, tunnel_exec: str = "tunnel.sh named", tunnel_extra: str = ""):
        (self.unit_dir / "simulearn-product.service").write_text(
            "[Service]\nExecStart=/bin/bash %h/dev/simulearn/scripts/serve_product.sh\n")
        (self.unit_dir / "simulearn-tunnel.service").write_text(
            f"[Unit]\n{tunnel_extra}[Service]\nExecStart=/bin/bash %h/dev/simulearn/scripts/{tunnel_exec}\n")

    def write_config(self, product_port: int):
        self.config.write_text(
            "tunnel: 0000\ncredentials-file: /home/x/.cloudflared/0000.json\ningress:\n"
            f"  - hostname: demo.example.org\n    service: http://127.0.0.1:{self.demo_port}\n"
            f"  - hostname: app.example.org\n    service: http://127.0.0.1:{product_port}\n"
            "  - service: http_status:404\n")

    def journal(self, unit: str, text: str):
        (self.state / f"journal-{unit}").write_text(text)

    def flag(self, name: str):
        (self.state / name).touch()

    def no_admin(self):
        (self.state / "admin").write_text("1")

    def active(self, unit: str) -> bool:
        return (self.state / f"active-{unit}").exists()

    def calls(self) -> list[str]:
        log = self.state / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def run(self, script: Path, *args: str, **env: str):
        full_env = {"PATH": str(self.bin), "HOME": str(self.home), "STUB_STATE": str(self.state),
                    "SIMULEARN_ENV_FILE": str(self.dotenv), "TUNNEL_CONFIG": str(self.config),
                    "SIMULEARN_VENV": str(self.tmp / "no-venv"), "SIMULEARN_FRONTEND_DIST": str(self.dist),
                    "DEMO_PORT": str(self.demo_port), "PRODUCT_UP_TUNNEL_WAIT_SECONDS": "1",
                    "PRODUCT_UP_WAIT_SECONDS": "2", "LANG": "C.UTF-8", **env}
        out = subprocess.run([shutil.which("bash"), str(script), *args], env=full_env, capture_output=True,
                             text=True, timeout=60, cwd=self.tmp)
        assert "hunter2-secret" not in out.stdout + out.stderr
        assert "dbsecret" not in out.stdout + out.stderr
        return out


@pytest.fixture
def b(tmp_path):
    box = Box(tmp_path)
    yield box
    box._demo_socket.close()


# --- serve_product.sh -----------------------------------------------------------------------------------------------

def server_argv(out) -> list[str]:
    lines = out.stdout.splitlines()
    return lines[lines.index("-m"):] if "-m" in lines else []


def test_serve_starts_the_server_on_localhost_8000_from_the_repo(b):
    out = b.run(SERVE)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines()[0] == str(PROJECT_ROOT)  # runs from the repo
    argv = server_argv(out)
    assert argv[:2] == ["-m", "src.product.server"]
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--port") + 1] == "8000"
    assert argv[argv.index("--device") + 1] == "auto"
    assert "--config" not in argv  # the server's own default
    assert "python scripts/create_user.py has-admin" in b.calls()


def test_serve_settings_come_from_the_environment_and_extra_args_pass_through(b):
    out = b.run(SERVE, "--extra", PRODUCT_PORT="8100", PRODUCT_DEVICE="cpu", PRODUCT_CONFIG="configs/x.yaml")
    assert out.returncode == 0, out.stderr
    argv = server_argv(out)
    assert argv[argv.index("--port") + 1] == "8100"
    assert argv[argv.index("--device") + 1] == "cpu"
    assert argv[argv.index("--config") + 1] == "configs/x.yaml"
    assert argv[-1] == "--extra"


def assert_server_not_started(b: Box, out):
    assert out.returncode != 0
    assert server_argv(out) == []
    assert not any("src.product.server" in c for c in b.calls())


def test_serve_refuses_without_the_built_frontend(b):
    (b.dist / "index.html").unlink()
    out = b.run(SERVE)
    assert_server_not_started(b, out)
    assert "scripts/build_frontend.sh" in out.stderr


def test_serve_refuses_while_the_demo_unit_is_active(b):
    b.flag("active-simulearn-demo")
    out = b.run(SERVE)
    assert_server_not_started(b, out)
    assert "demo" in out.stderr and "demo_down.sh" in out.stderr


def test_serve_refuses_while_something_listens_on_the_demo_port(b, listener):
    out = b.run(SERVE, DEMO_PORT=str(listener))
    assert_server_not_started(b, out)
    assert "demo_down.sh" in out.stderr


def test_serve_refuses_without_an_active_admin(b):
    b.no_admin()
    out = b.run(SERVE)
    assert_server_not_started(b, out)
    assert "create_user.py create <username> --role admin" in out.stderr


def test_serve_script_syntax():
    for script in (SERVE, UP, DOWN):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0


# --- create_user.py has-admin -----------------------------------------------------------------------------------------

def load_cli():
    spec = importlib.util.spec_from_file_location("create_user", PROJECT_ROOT / "scripts" / "create_user.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_has_admin_needs_an_active_admin_and_prints_no_accounts(capsys):
    cli = load_cli()
    auth = Auth(mongomock.MongoClient().simulearn)
    assert cli.main(["has-admin"], auth=auth) == 1  # nobody
    auth.create_user("teacher1", "Teacher", "correct horse battery", role="educator")
    assert cli.main(["has-admin"], auth=auth) == 1  # educators don't count
    auth.create_user("boss1", "Boss", "correct horse battery", role="admin")
    auth.set_disabled("boss1", True)
    assert cli.main(["has-admin"], auth=auth) == 1  # a disabled admin can't log in
    auth.set_disabled("boss1", False)
    assert cli.main(["has-admin"], auth=auth) == 0
    out = capsys.readouterr()
    assert "boss1" not in out.out + out.err and "teacher1" not in out.out + out.err


# --- product_up.sh: success -----------------------------------------------------------------------------------------

def test_up_starts_db_then_product_then_tunnel_and_prints_url_and_saving(b, listener):
    b.write_config(listener)
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    calls = b.calls()
    up = calls.index("docker compose up -d")
    product = calls.index("systemctl --user start simulearn-product")
    tunnel = calls.index("systemctl --user start simulearn-tunnel")
    assert up < product < tunnel
    assert "systemctl --user unset-environment SIMULEARN_SAVE_CHATS" in calls
    assert not any("simulearn-demo" in c and "start" in c for c in calls)  # never loads the demo too
    assert b.active("simulearn-product") and b.active("simulearn-tunnel")
    assert "Public URL: https://app.example.org" in out.stdout
    assert "demo.example.org" not in out.stdout  # only the product's hostname
    assert "SimuLearn: saving on" in out.stdout


def test_up_no_save_turns_saving_off_but_still_starts_mongo(b, listener):
    b.write_config(listener)
    b.journal("simulearn-product", "SimuLearn: saving OFF (SIMULEARN_SAVE_CHATS=0); frontend ...\n")
    out = b.run(UP, "--no-save", PRODUCT_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    calls = b.calls()
    assert "docker compose up -d" in calls  # accounts live in MongoDB
    assert calls.index("systemctl --user set-environment SIMULEARN_SAVE_CHATS=0") < \
        calls.index("systemctl --user start simulearn-product")
    assert "SimuLearn: saving OFF (SIMULEARN_SAVE_CHATS=0)" in out.stdout


def test_up_twice_is_fine(b, listener):
    b.write_config(listener)
    assert b.run(UP, PRODUCT_PORT=str(listener)).returncode == 0
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode == 0, out.stderr
    assert "Public URL: https://app.example.org" in out.stdout


# --- product_up.sh: refusals ----------------------------------------------------------------------------------------

def assert_nothing_started(b: Box):
    assert not any(c.startswith(("systemctl --user start", "docker compose up")) for c in b.calls())


@pytest.mark.parametrize("unit", ["simulearn-product", "simulearn-tunnel"])
def test_up_refuses_when_a_unit_is_not_installed(b, listener, unit):
    b.write_config(listener)
    (b.unit_dir / f"{unit}.service").unlink()
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and f"{unit}.service is not installed" in out.stderr
    assert_nothing_started(b)


def test_up_refuses_a_quick_tunnel_unit(b, listener):
    b.write_config(listener)
    b.install_units(tunnel_exec="tunnel.sh quick")
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "tunnel.sh named" in out.stderr
    assert_nothing_started(b)


def test_up_refuses_an_old_tunnel_unit_that_starts_the_demo(b, listener):
    b.write_config(listener)
    b.install_units(tunnel_extra="Wants=simulearn-demo.service network-online.target\n")
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "Copy the new scripts/systemd/simulearn-tunnel.service" in out.stderr
    assert_nothing_started(b)


def test_up_refuses_a_config_without_a_product_hostname(b, listener):
    b.write_config(free_port())  # the product's rule points somewhere else
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "no ingress rule" in out.stderr and "config.yml.example" in out.stderr
    assert_nothing_started(b)


def test_up_refuses_a_missing_config(b, listener):
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "is missing" in out.stderr
    assert_nothing_started(b)


@pytest.mark.parametrize("dotenv_line,env", [
    ("SIMULEARN_COOKIE_SECURE=0\n", {}),
    ("SIMULEARN_COOKIE_SECURE=false\n", {}),
    ("", {"SIMULEARN_COOKIE_SECURE": "off"}),
])
def test_up_refuses_an_insecure_cookie_behind_the_tunnel(b, listener, dotenv_line, env):
    b.write_config(listener)
    b.dotenv.write_text(b.dotenv.read_text() + dotenv_line)
    out = b.run(UP, PRODUCT_PORT=str(listener), **env)
    assert out.returncode != 0 and "SIMULEARN_COOKIE_SECURE" in out.stderr
    assert_nothing_started(b)


def test_up_accepts_an_explicitly_secure_cookie(b, listener):
    b.write_config(listener)
    b.dotenv.write_text(b.dotenv.read_text() + "SIMULEARN_COOKIE_SECURE=1\n")
    assert b.run(UP, PRODUCT_PORT=str(listener)).returncode == 0


def test_up_refuses_while_the_demo_runs(b, listener):
    b.write_config(listener)
    b.flag("active-simulearn-demo")
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "demo_down.sh --keep-db" in out.stderr
    assert_nothing_started(b)


def test_up_refuses_without_docker(b, listener):
    b.write_config(listener)
    b.remove("docker")
    out = b.run(UP, PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "docker is not on PATH" in out.stderr
    assert_nothing_started(b)


def test_up_reports_a_refusal_from_serve_product_right_away(b):
    port = free_port()  # the product never listens
    b.write_config(port)
    b.journal("simulearn-product", "serve_product.sh: no active admin account, so nobody could log in\n")
    out = b.run(UP, PRODUCT_PORT=str(port), PRODUCT_UP_WAIT_SECONDS="600")
    assert out.returncode != 0
    assert "refused to start" in out.stderr and "no active admin account" in out.stderr
    assert "systemctl --user start simulearn-tunnel" not in b.calls()


def test_up_times_out_when_the_product_never_listens(b):
    port = free_port()
    b.write_config(port)
    out = b.run(UP, PRODUCT_PORT=str(port), PRODUCT_UP_WAIT_SECONDS="1")
    assert out.returncode != 0
    assert "after 1 s" in out.stderr and "journalctl --user -u simulearn-product" in out.stderr


def test_up_rejects_the_old_no_db_flag(b, listener):
    b.write_config(listener)
    out = b.run(UP, "--no-db", PRODUCT_PORT=str(listener))
    assert out.returncode != 0 and "usage" in out.stderr
    assert_nothing_started(b)


# --- product_down.sh ------------------------------------------------------------------------------------------------

def test_down_stops_tunnel_and_product_then_the_db_and_shows_gpu(b):
    b.flag("active-simulearn-product")
    b.flag("active-simulearn-tunnel")
    out = b.run(DOWN)
    assert out.returncode == 0, out.stderr
    calls = b.calls()
    assert calls.index("systemctl --user stop simulearn-tunnel") < calls.index("systemctl --user stop simulearn-product")
    assert calls.index("systemctl --user stop simulearn-product") < calls.index("docker compose stop")
    assert "systemctl --user unset-environment SIMULEARN_SAVE_CHATS" in calls
    assert not b.active("simulearn-product") and not b.active("simulearn-tunnel")
    assert "321 MiB" in out.stdout


def test_down_keep_db_leaves_mongo_alone(b):
    out = b.run(DOWN, "--keep-db")
    assert out.returncode == 0, out.stderr
    assert "docker compose stop" not in b.calls()
    assert "systemctl --user stop simulearn-product" in b.calls()


def test_down_twice_is_fine(b):
    assert b.run(DOWN).returncode == 0
    assert b.run(DOWN).returncode == 0


def test_down_fails_loudly_when_the_product_cannot_be_stopped(b):
    b.flag("active-simulearn-product")
    b.flag("stop-fails")
    out = b.run(DOWN)
    assert out.returncode != 0 and "VRAM" in out.stderr


def test_down_rejects_unknown_flags(b):
    out = b.run(DOWN, "--no-db")
    assert out.returncode != 0 and "usage" in out.stderr
    assert b.calls() == []


# --- systemd unit ---------------------------------------------------------------------------------------------------

def unit_keys() -> dict[str, str]:
    keys = {}
    for line in UNIT.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith(("#", ";")):
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    return keys


def test_unit_runs_the_serve_script_and_restarts_on_failure():
    keys = unit_keys()
    assert "scripts/serve_product.sh" in keys["ExecStart"]
    assert keys["Restart"] == "on-failure"
    assert keys["WantedBy"] == "default.target"  # a user unit, not a system one
    assert "simulearn-demo" not in UNIT.read_text().split("[Unit]", 1)[1]  # never pulls in the demo


def test_unit_carries_no_secrets():
    text = UNIT.read_text()
    for secret in ("DEMO_PASSWORD", "MONGODB_URI", "HF_TOKEN", "SIMULEARN_COOKIE_SECURE"):
        assert f"{secret}=" not in text
