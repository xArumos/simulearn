"""HiPerGator SLURM scripts: syntax, the dry-run job chain, and config resolution for every job."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from src.utils.config import PROJECT_ROOT, load_config

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

SLURM = PROJECT_ROOT / "scripts" / "slurm"
SCRIPTS = [PROJECT_ROOT / "scripts" / "env_hpg.sh", SLURM / "submit_all.sh", SLURM / "train.sbatch", SLURM / "evaluate.sbatch"]
STAMP = "20990101-0000"
SMOKE = {"configs/hpg/phase1/qwen1.5b_lora_smoke_hpg.yaml", "configs/hpg/phase2/qwen7b_qlora_smoke_hpg.yaml"}
JOB_LINE = re.compile(r"^(JOB_\d+) = (sbatch .*)$")


def run_submit(*args: str, env_file: str = "scripts/slurm/hpg.env.example") -> subprocess.CompletedProcess:
    env = {**os.environ, "HPG_ENV_FILE": env_file}
    return subprocess.run(["bash", str(SLURM / "submit_all.sh"), *args], cwd=PROJECT_ROOT, env=env,
                          capture_output=True, text=True, timeout=60)


def parse_jobs(stdout: str) -> dict[str, dict]:
    """JOB_n -> {script, config, run_id, adapter, deps, opts} from the dry-run lines."""
    jobs = {}
    for line in stdout.splitlines():
        m = JOB_LINE.match(line)
        if not m:
            continue
        argv = shlex.split(m.group(2))
        script_i = next(i for i, a in enumerate(argv) if a.endswith(".sbatch"))
        opts = dict(zip(argv[2:script_i:2], argv[3:script_i:2]))  # skip "sbatch --parsable"
        pos = argv[script_i + 1:]
        dep = opts.get("--dependency", "")
        jobs[m.group(1)] = {
            "script": argv[script_i], "config": pos[0], "run_id": pos[1], "adapter": pos[2] if len(pos) > 2 else None,
            "deps": dep.removeprefix("afterok:").split(":") if dep else [], "opts": opts,
        }
    return jobs


@pytest.fixture(scope="module")
def chain() -> dict[str, dict]:
    r = run_submit("--dry-run", "--stamp", STAMP)
    assert r.returncode == 0, r.stderr
    jobs = parse_jobs(r.stdout)
    assert jobs, r.stdout
    return jobs


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bash_syntax(script: Path):
    r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_hpg_config_is_in_the_chain_and_loads(chain):
    used = {j["config"] for j in chain.values()}
    on_disk = {str(p.relative_to(PROJECT_ROOT)) for p in (PROJECT_ROOT / "configs" / "hpg").rglob("*.yaml")}
    assert used == on_disk
    for job in chain.values():
        cfg = load_config(PROJECT_ROOT / job["config"])
        assert job["run_id"] == f"{STAMP}_{cfg['run_name']}"
        assert job["opts"]["--output"].startswith(f"experiments/{job['run_id']}/slurm-")
        assert {"model", "data", "eval"} <= cfg.keys()
        if job["script"].endswith("train.sbatch"):
            assert {"lora", "train"} <= cfg.keys(), job["config"]


def test_dependencies(chain):
    order = list(chain)
    for jid, job in chain.items():  # every dependency is an earlier job
        assert all(order.index(d) < order.index(jid) for d in job["deps"]), jid

    trains = {j["run_id"]: jid for jid, j in chain.items() if j["script"].endswith("train.sbatch")}
    evals = {jid: j for jid, j in chain.items() if j["script"].endswith("evaluate.sbatch")}
    smoke_evals = sorted(jid for jid, j in evals.items() if j["config"] in SMOKE)
    assert len(smoke_evals) == 2

    for jid, job in evals.items():  # trained runs: eval waits for its own train job and loads its adapter
        if job["run_id"] in trains:
            assert job["deps"] == [trains[job["run_id"]]]
            assert job["adapter"] == f"experiments/{job['run_id']}/adapter"
        else:  # Phase 0 baselines: no adapter, gated on the smoke tests
            assert job["adapter"] is None
            assert "/phase0/" in job["config"]
            assert sorted(job["deps"]) == smoke_evals
    for run_id, jid in trains.items():
        job = chain[jid]
        assert job["deps"] == ([] if job["config"] in SMOKE else smoke_evals), run_id
    assert len(trains) == 7 and len(evals) == 11


AGE4 = "configs/hpg/phase3/qwen1.5b_lora_ep1_age4_hpg.yaml"


def test_age4_config_is_run3_recipe_on_age4():
    age4 = load_config(PROJECT_ROOT / AGE4)
    run3 = load_config(PROJECT_ROOT / "configs/hpg/phase1/qwen1.5b_lora_ep1_hpg.yaml")
    local = load_config(PROJECT_ROOT / "configs/phase3/qwen1.5b_lora_ep1_age4.yaml")
    assert age4["run_name"] == "qwen1.5b_lora_ep1_age4_hpg"
    assert age4["age_label"] == 4 and age4["data"]["bucket"] == "age4"
    for key in ("model", "lora", "train", "eval"):
        assert age4[key] == run3[key] == local[key], key
    assert {k: v for k, v in age4["data"].items() if k != "bucket"} == {
        k: v for k, v in run3["data"].items() if k != "bucket"}


def test_age4_in_chain_after_smoke(chain):
    jobs = [j for j in chain.values() if j["config"] == AGE4]
    assert sorted(j["script"].rsplit("/", 1)[1] for j in jobs) == ["evaluate.sbatch", "train.sbatch"]


def test_only_submits_one_run_without_the_smoke_gate():
    r = run_submit("--dry-run", "--only", "qwen1.5b_lora_ep1_age4_hpg", "--stamp", STAMP)
    assert r.returncode == 0, r.stderr
    jobs = parse_jobs(r.stdout)
    assert len(jobs) == 2 and {j["config"] for j in jobs.values()} == {AGE4}
    train, ev = jobs["JOB_1"], jobs["JOB_2"]
    assert train["script"].endswith("train.sbatch") and train["deps"] == []
    assert ev["script"].endswith("evaluate.sbatch") and ev["deps"] == ["JOB_1"]
    assert ev["adapter"] == f"experiments/{STAMP}_qwen1.5b_lora_ep1_age4_hpg/adapter"


def test_only_baseline_is_eval_only():
    r = run_submit("--dry-run", "--only", "qwen1.5b_base-default_hpg", "--stamp", STAMP)
    assert r.returncode == 0, r.stderr
    jobs = parse_jobs(r.stdout)
    assert len(jobs) == 1 and jobs["JOB_1"]["script"].endswith("evaluate.sbatch") and jobs["JOB_1"]["deps"] == []


def test_only_rejects_unknown_run_and_smoke_only():
    r = run_submit("--dry-run", "--only", "no_such_run")
    assert r.returncode != 0 and "no_such_run" in r.stderr
    r = run_submit("--dry-run", "--only", "qwen1.5b_lora_ep1_age4_hpg", "--smoke-only")
    assert r.returncode != 0


def test_smoke_only():
    r = run_submit("--dry-run", "--smoke-only", "--stamp", STAMP)
    assert r.returncode == 0, r.stderr
    jobs = parse_jobs(r.stdout)
    assert {j["config"] for j in jobs.values()} == SMOKE and len(jobs) == 4


def test_settings_come_from_env_file(chain):
    env = dict(re.findall(r"^(HPG_\w+)=(\S*)", (SLURM / "hpg.env.example").read_text(), re.M))
    for job in chain.values():
        o = job["opts"]
        assert (o["--account"], o["--qos"], o["--partition"], o["--gpus"]) == (
            env["HPG_ACCOUNT"], env["HPG_QOS"], env["HPG_PARTITION"], env["HPG_GPUS"])
    for p in (SLURM / "train.sbatch", SLURM / "evaluate.sbatch"):
        sbatch_lines = [ln for ln in p.read_text().splitlines() if ln.startswith("#SBATCH")]
        assert not any(k in ln for ln in sbatch_lines for k in ("--account", "--qos", "--partition", "--gpus", "--time"))


def test_real_submit_refuses_missing_or_placeholder_settings(tmp_path):
    r = run_submit(env_file=str(tmp_path / "missing.env"))
    assert r.returncode != 0 and "not found" in r.stderr
    r = run_submit(env_file="scripts/slurm/hpg.env.example")  # placeholders must be replaced before a real submit
    assert r.returncode != 0 and "placeholder" in r.stderr


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_hpg_env_is_git_ignored():
    def ignored(path: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT).returncode == 0
    assert ignored("scripts/slurm/hpg.env")
    assert not ignored("scripts/slurm/hpg.env.example")
