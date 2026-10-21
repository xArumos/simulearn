import json

import pytest

from src.data.child_ids import UnionFind, child_id, linked_ids
from src.data.split import check_no_leakage, pick_golden, split_groups
from src.utils.config import resolve


def test_child_id_rules():
    assert child_id("HSLLD", "Eng-NA/HSLLD/HV1/MT/abcmt1.cha", "CHI", {"rule": "regex", "pattern": "^([a-z]{3})"}) == "HSLLD/abc"
    assert child_id("Mac", "Eng-NA/Mac/010203.cha", "MAR", {"rule": "participant_code"}) == "Mac/MAR"
    assert child_id("OCSC", "Eng-NA/OCSC/5/5001.cha", "CHI", None) == "OCSC/5/5001:CHI"
    assert linked_ids("HSLLD", "x/abc_defbr1.cha", {"link_pattern": "^([a-z]{3})[a-z0-9]*_([a-z]{3})"}) == ["HSLLD/abc", "HSLLD/def"]


def test_union_find_groups():
    uf = UnionFind()
    uf.union("C/b", "C/a")
    uf.union("C/c", "C/b")
    uf.find("C/z")
    g = uf.groups()
    assert g["C/c"] == "C/a" and g["C/z"] == "C/z"


def test_split_deterministic_and_grouped():
    group_of = {f"A/{i}": f"A/{i}" for i in range(50)}
    group_of["A/1"] = group_of["A/2"] = "A/1"          # linked children
    s1, s2 = split_groups(group_of), split_groups(group_of)
    assert s1 == s2
    where = {c: n for n, kids in s1.items() for c in kids}
    assert where["A/1"] == where["A/2"]
    assert sum(len(v) for v in s1.values()) == 50
    assert len(s1["test"]) == 5 and len(s1["val"]) == 5


def test_leakage_check_catches_shared_file():
    splits = {"train": ["A/1"], "val": [], "test": ["A/2"]}
    with pytest.raises(AssertionError):
        check_no_leakage(splits, {"A/1": {"f.cha"}, "A/2": {"f.cha"}})
    with pytest.raises(AssertionError):
        check_no_leakage({"train": ["A/1"], "val": ["A/1"], "test": []}, {})
    check_no_leakage(splits, {"A/1": {"f.cha"}, "A/2": {"g.cha"}})


def test_golden_limits_per_child():
    exs = [{"id": f"e{i}", "messages": [0] * 6, "meta": {"corpus": "A" if i % 2 else "B", "child_id": f"k{i % 5}"}} for i in range(40)]
    g = pick_golden(exs, n=30, per_child=2)
    assert len(g) == 10                                 # 5 children x 2


# --- Leakage test on the real processed data (skipped until preprocessing has run) -------------
PROCESSED = resolve("data/processed")


@pytest.mark.parametrize("bucket", ["age5", "age4"])
def test_real_data_no_leakage(bucket):
    d = PROCESSED / bucket
    if not (d / "train.jsonl").exists():
        pytest.skip("processed data not present")
    kids, files = {}, {}
    for name in ("train", "val", "test"):
        for line in open(d / f"{name}.jsonl", encoding="utf-8"):
            m = json.loads(line)["meta"]
            assert kids.setdefault(m["child_id"], name) == name, f"child {m['child_id']} leaks"
            assert files.setdefault(m["file"], name) == name, f"file {m['file']} leaks"
            assert kids.setdefault("group:" + m["group_id"], name) == name, f"group {m['group_id']} leaks"
    golden = [json.loads(l)["meta"]["child_id"] for l in open(d / "golden_review.jsonl", encoding="utf-8")]
    assert all(kids[c] == "test" for c in golden)
