"""The age6 bucket (72-83 months) must not change the age4/age5 data or splits.

Builds a small invented multi-corpus tree (no CHILDES text), runs preprocessing with and
without ``split_extra_age_range``, and compares the outputs.
"""
import copy
import json

import pytest

from src.data.preprocess import run
from src.utils.config import load_config, resolve
from tests.fake_chat import FAKE


def _with_age(age: str, birth: str = "01-JAN-2000") -> str:
    return FAKE.replace("5;02.10", age).replace("01-JAN-2000", birth)


@pytest.fixture()
def raw_tree(tmp_path):
    root = tmp_path / "raw"
    ages = ["4;03.", "4;09.", "5;02.", "5;08.", "6;01.", "6;07.", "6;11."]
    # OCSC-style: one child per file.
    for i in range(40):
        d = root / "Eng-NA" / "OCSC" / "6"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{6000 + i}.cha").write_text(_with_age(ages[i % len(ages)]), encoding="utf-8")
    # HSLLD-style: same 3-letter child across visits, at age 5 and again at age 6.
    for k, code in enumerate(["abc", "def", "ghi", "jkl", "mno", "pqr", "stu", "vwx", "yza", "bcd",
                              "efg", "hij"]):
        for visit, age in [(1, "4;06."), (2, "5;06."), (3, "6;06.")]:
            d = root / "Eng-NA" / "HSLLD" / f"HV{visit}" / "MT"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{code}mt{visit}.cha").write_text(_with_age(age, f"0{k % 9 + 1}-MAR-2001"),
                                                     encoding="utf-8")
    # HSLLD children seen ONLY at age 6.
    for code in ["zzz", "yyy", "xxw", "www2"][:3]:
        d = root / "Eng-NA" / "HSLLD" / "HV5" / "MT"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{code}mt5.cha").write_text(_with_age("6;03.", "15-JUN-1999"), encoding="utf-8")
    return root


def _cfg(raw, out, extra: bool):
    cfg = copy.deepcopy(load_config(resolve("configs/data_default.yaml")))
    cfg["raw_dir"] = str(raw)
    cfg["processed_dir"] = str(out)
    cfg["collections"] = ["Eng-NA"]
    cfg["corpora"] = ["OCSC", "HSLLD"]
    cfg["child_id_rules"]["HSLLD"]["link_by_birth"] = False
    if not extra:
        cfg.pop("split_extra_age_range")
        cfg["buckets"].pop("age6")
    return cfg


def _read(path):
    return path.read_text(encoding="utf-8")


def test_age6_added_without_changing_age4_age5(raw_tree, tmp_path, capsys):
    before, after = tmp_path / "before", tmp_path / "after"
    run(_cfg(raw_tree, before, extra=False), ["age5", "age4"], verify=False)
    run(_cfg(raw_tree, after, extra=True), ["age5", "age4", "age6"], verify=False)
    capsys.readouterr()

    # 1. age4/age5 examples and splits are byte-identical.
    for bucket in ["age5", "age4"]:
        for name in ["train.jsonl", "val.jsonl", "test.jsonl", "golden_review.jsonl", "splits.json"]:
            assert _read(before / bucket / name) == _read(after / bucket / name), f"{bucket}/{name} changed"

    # 2. age6 exists, uses a 6-year-old prompt, and only contains 72-83 month views.
    rows = {s: [json.loads(l) for l in _read(after / "age6" / f"{s}.jsonl").splitlines()]
            for s in ["train", "val", "test"]}
    all_rows = [r for rs in rows.values() for r in rs]
    assert all_rows, "age6 bucket is empty"
    assert all(72 <= r["meta"]["age_months"] <= 83 for r in all_rows)
    assert all("6-year-old" in r["messages"][0]["content"] for r in all_rows)

    # 3. A child seen at age 5 keeps the same split at age 6.
    split5 = {}
    for s in ["train", "val", "test"]:
        for l in _read(after / "age5" / f"{s}.jsonl").splitlines():
            split5[json.loads(l)["meta"]["child_id"]] = s
    for s, rs in rows.items():
        for r in rs:
            cid = r["meta"]["child_id"]
            if cid in split5:
                assert split5[cid] == s, f"{cid} is {split5[cid]} at age 5 but {s} at age 6"

    # 4. No child, file, or group appears in two splits across all three buckets.
    seen = {}
    for bucket in ["age4", "age5", "age6"]:
        for s in ["train", "val", "test"]:
            for l in _read(after / bucket / f"{s}.jsonl").splitlines():
                m = json.loads(l)["meta"]
                for key in (m["child_id"], "file:" + m["file"], "group:" + m["group_id"]):
                    assert seen.setdefault(key, s) == s, f"{key} leaks"

    # 5. Children new at age 6 are split too (stratified), not all dumped in train.
    new_kids = {r["meta"]["child_id"] for r in all_rows} - set(split5)
    assert new_kids
    top = json.loads(_read(after / "splits.json"))
    assert top["extra_age_range_months"] == [72, 83]
    assert all(any(k in top[s] for s in ["train", "val", "test"]) for k in new_kids)


def test_auto_age_label_states_each_childs_age(raw_tree, tmp_path, capsys):
    cfg = _cfg(raw_tree, tmp_path / "out", extra=True)
    cfg["buckets"]["age4to6"] = {"min_months": 48, "max_months": 83, "age_label": "auto"}
    run(cfg, ["age4to6", "age6"], verify=False)
    capsys.readouterr()
    rows = [json.loads(l) for s in ["train", "val", "test"]
            for l in _read(tmp_path / "out" / "age4to6" / f"{s}.jsonl").splitlines()]
    ages = {r["meta"]["age_months"] // 12 for r in rows}
    assert ages == {4, 5, 6}
    for r in rows:
        assert f"{r['meta']['age_months'] // 12}-year-old" in r["messages"][0]["content"]
    # The mixed bucket uses the same splits as the single-age buckets.
    split6 = {json.loads(l)["meta"]["child_id"]: s for s in ["train", "val", "test"]
              for l in _read(tmp_path / "out" / "age6" / f"{s}.jsonl").splitlines()}
    for s in ["train", "val", "test"]:
        for l in _read(tmp_path / "out" / "age4to6" / f"{s}.jsonl").splitlines():
            cid = json.loads(l)["meta"]["child_id"]
            assert split6.get(cid, s) == s


def test_eval_bucket_used_for_validation(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    import src.train.sft_lora as sft
    for bucket, n in [("age5to6", 5), ("age6", 2)]:
        d = tmp_path / bucket
        d.mkdir()
        for split in ["train", "val"]:
            with open(d / f"{split}.jsonl", "w") as f:
                for i in range(n):
                    f.write(json.dumps({"id": f"{bucket}{i}", "messages": [
                        {"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                        {"role": "assistant", "content": bucket}]}) + "\n")
    seen = []
    monkeypatch.setattr(sft, "encode_example", lambda tok, msgs, L: seen.append(msgs[-1]["content"]) or
                        {"input_ids": [1], "labels": [1], "n_context_turns_used": 1})
    cfg = {"data": {"processed_dir": str(tmp_path), "bucket": "age5to6", "eval_bucket": "age6"}}
    sft.load_split(cfg, "train", None, 0, None, 512, {})
    assert set(seen) == {"age5to6"}
    seen.clear()
    sft.load_split(cfg, "val", None, 0, None, 512, {})
    assert set(seen) == {"age6"}
