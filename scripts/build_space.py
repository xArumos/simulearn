"""Assemble the Hugging Face Space folder from an explicit allowlist of files, so no data can slip in.

    python scripts/build_space.py [--out build/space]

Then upload it (you must be logged in with `hf auth login` yourself):
    hf upload <hf-user>/simulearn-demo build/space . --repo-type space
Adapters go to a separate private model repo: scripts/upload_adapters.sh.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# (source relative to the repo root, destination relative to the Space root)
FILES = [
    ("space/app.py", "app.py"),
    ("space/requirements.txt", "requirements.txt"),
    ("space/README.md", "README.md"),
    ("configs/demo.yaml", "configs/demo.yaml"),
    ("src/__init__.py", "src/__init__.py"),
    ("src/demo/__init__.py", "src/demo/__init__.py"),
    ("src/demo/chat_demo.py", "src/demo/chat_demo.py"),
    ("src/demo/store.py", "src/demo/store.py"),
    ("src/utils/__init__.py", "src/utils/__init__.py"),
    ("src/utils/config.py", "src/utils/config.py"),
    ("src/utils/modeling.py", "src/utils/modeling.py"),
    ("src/utils/prompts.py", "src/utils/prompts.py"),
    ("backend/__init__.py", "backend/__init__.py"),
    ("backend/app/__init__.py", "backend/app/__init__.py"),
    ("backend/app/main.py", "backend/app/main.py"),
]
FORBIDDEN_SUFFIXES = {".cha", ".jsonl", ".zip", ".safetensors", ".bin", ".csv"}


def build(out: Path) -> list[Path]:
    if out.exists():
        shutil.rmtree(out)
    written = []
    for src, dst in FILES:
        target = out / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / src, target)
        written.append(target)
    bad = [p for p in out.rglob("*") if p.suffix in FORBIDDEN_SUFFIXES or "data" in p.relative_to(out).parts]
    if bad:
        raise SystemExit(f"refusing to build: data-like files in the bundle: {bad}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "space"))
    out = Path(ap.parse_args().out)
    for p in build(out):
        print(p.relative_to(out).as_posix())
    print(f"\nSpace folder ready: {out}")


if __name__ == "__main__":
    main()
