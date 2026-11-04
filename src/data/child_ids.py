"""Stable child IDs and leakage-safe split groups.

child_id = "<corpus>/<id>". How <id> is derived is set per corpus in the data config:
  rule: file             -> file path without extension (one child per file; the default)
  rule: regex            -> first capture group of `pattern` on the file name
  rule: participant_code -> the target child's participant code (longitudinal corpora like MacWhinney)

Split groups: children that might be the same person, or that share a transcript, must be in the
same split. We link child IDs with union-find when they
  - appear as target children in the same file,
  - are named together in one file name (`link_pattern`, all capture groups are linked), or
  - share an exact birth date + sex (`link_by_birth`; HSLLD uses several codes per child).
Over-linking only puts extra children in the same split, which is harmless. Under-linking leaks.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath


def child_id(corpus: str, rel_path: str, code: str, rule: dict | None) -> str:
    rule = rule or {"rule": "file"}
    p = PurePosixPath(rel_path)
    kind = rule.get("rule", "file")
    if kind == "regex":
        m = re.search(rule["pattern"], p.name)
        if m:
            return f"{corpus}/{m.group(1)}"
    elif kind == "participant_code":
        return f"{corpus}/{code}"
    stem = p.with_suffix("").as_posix().split("/", 2)[-1]  # drop "<collection>/<corpus>/"
    return f"{corpus}/{stem}:{code}"


def linked_ids(corpus: str, rel_path: str, rule: dict | None) -> list[str]:
    if not rule or "link_pattern" not in rule:
        return []
    m = re.search(rule["link_pattern"], PurePosixPath(rel_path).name)
    return [f"{corpus}/{g}" for g in m.groups() if g] if m else []


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Deterministic representative: the smaller ID.
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo

    def groups(self) -> dict[str, str]:
        return {x: self.find(x) for x in self.parent}
