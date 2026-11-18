"""Local MongoDB setup (issue #13): .env loading, compose port binding, backup script."""
import os
import re
import stat
import subprocess
from pathlib import Path

import mongomock
import pytest

from backend.app.env import load_env_file

ROOT = Path(__file__).resolve().parents[2]


def test_env_file_sets_missing_variables_only(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n\n"
        "MONGODB_URI=mongodb://127.0.0.1:27017\n"
        "export MONGODB_DATABASE='simulearn_test'\n"
        'DEMO_PASSWORD="already set elsewhere"\n'
        "EMPTY=\n"
        "not a variable line\n"
    )
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)
    monkeypatch.delenv("EMPTY", raising=False)
    monkeypatch.setenv("DEMO_PASSWORD", "from-shell")

    loaded = load_env_file(env)

    assert os.environ["MONGODB_URI"] == "mongodb://127.0.0.1:27017"
    assert os.environ["MONGODB_DATABASE"] == "simulearn_test"
    assert os.environ["DEMO_PASSWORD"] == "from-shell"  # the shell wins over .env
    assert os.environ["EMPTY"] == ""
    assert set(loaded) == {"MONGODB_URI", "MONGODB_DATABASE", "EMPTY"}


def test_missing_env_file_is_fine(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == {}


def test_env_example_matches_what_the_code_reads():
    example = (ROOT / ".env.example").read_text()
    keys = dict(re.findall(r"^([A-Z_]+)=(.*)$", example, flags=re.M))
    assert keys["MONGODB_URI"] == "mongodb://127.0.0.1:27017"
    assert keys["MONGODB_DATABASE"] == "simulearn"
    assert keys["DEMO_PASSWORD"] == ""  # never a real password in git
    code = (ROOT / "src/demo/store.py").read_text() + (ROOT / "backend/app/main.py").read_text()
    for key in ("MONGODB_URI", "MONGODB_DATABASE"):
        assert f'"{key}"' in code


def test_empty_uri_from_env_file_keeps_demo_saving_off(tmp_path, monkeypatch):
    from src.demo.store import DemoStore

    (tmp_path / ".env").write_text("MONGODB_URI=\n")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    load_env_file(tmp_path / ".env")
    assert not DemoStore.from_env().enabled


def test_demo_saves_when_env_points_at_a_database(monkeypatch):
    """With MONGODB_URI set, DemoStore.from_env connects and saves (pymongo swapped for mongomock)."""
    import pymongo

    from src.demo.store import DemoStore

    client = mongomock.MongoClient()
    monkeypatch.setattr(pymongo, "MongoClient", lambda *a, **k: client)
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "simulearn_test")
    store = DemoStore.from_env()
    assert store.enabled
    conv = store.start("tester", 5, ["fine-tuned"])["fine-tuned"]
    assert store.log_turn(conv, "tester", "hi", "hi", "m", {}) == 1
    assert client["simulearn_test"]["transcript_iterations"].count_documents({}) == 1


def test_backend_reads_same_variables(monkeypatch):
    from fastapi.testclient import TestClient

    import backend.app.main as main

    client = mongomock.MongoClient()
    seen = {}

    def fake_client(uri, **kwargs):
        seen["uri"] = uri
        return client

    monkeypatch.setattr(main, "MongoClient", fake_client)
    monkeypatch.setattr(main, "load_env_file", lambda *a, **k: {})
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "simulearn_test")
    with TestClient(main.create_app()) as api:
        r = api.post("/api/v1/conversations", json={"owner_id": "o", "title": "t"})
        assert r.status_code == 201
    assert seen["uri"] == "mongodb://127.0.0.1:27017"
    assert client["simulearn_test"]["conversations"].count_documents({}) == 1


def test_compose_binds_mongo_to_localhost_only():
    compose = (ROOT / "docker-compose.yml").read_text()
    ports = re.findall(r'^\s*-\s*"?([^"\s]+:27017)"?\s*$', compose, flags=re.M)
    assert ports, "mongo service must publish 27017"
    assert all(p.startswith("127.0.0.1:") for p in ports), ports
    assert "image: mongo:" in compose


@pytest.fixture
def fake_mongodump(tmp_path):
    """A stand-in mongodump that records its arguments and writes the --archive file."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "args.txt"
    script = bin_dir / "mongodump"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" > "{log}"\n'
        'for a in "$@"; do case "$a" in --archive=*) out="${a#--archive=}";; esac; done\n'
        'echo dumped > "$out"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir, log


def run_backup(env_extra, *args):
    env = {**os.environ, **env_extra}
    return subprocess.run(["bash", str(ROOT / "scripts/db_backup.sh"), *args],
                          capture_output=True, text=True, env=env, cwd=ROOT)


def test_backup_script_writes_timestamped_dump_outside_repo(tmp_path, fake_mongodump):
    bin_dir, log = fake_mongodump
    dest = tmp_path / "backups"
    r = run_backup({"PATH": f"{bin_dir}:{os.environ['PATH']}", "MONGODB_URI": "mongodb://127.0.0.1:27017",
                    "MONGODB_DATABASE": "simulearn", "SIMULEARN_BACKUP_DIR": str(dest)})
    assert r.returncode == 0, r.stderr
    dumps = list(dest.iterdir())
    assert len(dumps) == 1 and re.fullmatch(r"simulearn-\d{8}-\d{6}\.archive\.gz", dumps[0].name)
    assert dumps[0].read_text() == "dumped\n"
    args = log.read_text()
    assert "--uri=mongodb://127.0.0.1:27017" in args and "--db=simulearn" in args and "--gzip" in args


def test_backup_script_refuses_a_folder_inside_the_repo(tmp_path, fake_mongodump):
    bin_dir, _ = fake_mongodump
    r = run_backup({"PATH": f"{bin_dir}:{os.environ['PATH']}", "SIMULEARN_BACKUP_DIR": str(ROOT / "backups")})
    assert r.returncode != 0 and "inside the repo" in r.stderr
    assert not (ROOT / "backups").exists()


def test_backup_script_explains_missing_mongodump(tmp_path):
    r = run_backup({"PATH": "/usr/bin:/bin", "SIMULEARN_BACKUP_DIR": str(tmp_path / "b")})
    assert r.returncode != 0 and "mongodump" in r.stderr
