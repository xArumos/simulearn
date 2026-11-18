"""Read KEY=value lines from the repo's `.env` into os.environ (no extra dependency).

Used by the demo (src/demo/chat_demo.py) and the transcript API (backend/app/main.py) so both see the same
MONGODB_URI / MONGODB_DATABASE / DEMO_PASSWORD. Variables already set in the shell win over `.env`.
`.env` is git-ignored; `.env.example` is the template.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env_file(path: Optional[Union[str, Path]] = None) -> dict[str, str]:
    """Set each variable from `path` (default: <repo>/.env) that isn't set yet; returns the ones it set."""
    path = Path(path) if path is not None else REPO_ROOT / ".env"
    if not path.is_file():
        return {}
    loaded = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        key, value = m.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded
