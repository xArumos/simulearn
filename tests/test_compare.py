import json

import pytest

from src.eval import compare


def _gen(mean_words=5.0, degen=0.01, short=0.2, dist2=0.6):
    return {
        "mean_words": mean_words, "median_words": 3.0, "over_20_words_rate": 0.02,
        "msttr_100": 0.65, "oov_rate": 0.01, "rare_word_rate": 0.05, "filler_rate": 0.13,
        "short_answer_rate": short, "repetition_rate": 0.05, "nonstandard_rate": 0.06,
        "silence_rate": 0.05, "degenerate_rate": degen, "meta_rate": 0.0,
        "continues_other_side_rate": 0.0, "distinct_1": 0.15, "distinct_2": dist2,
    }


def _run(tmp_path, run_id, bucket="age5", split="val", n=1000, ks=0.03, gap=0.02, loss=2.2, **gen):
    d = tmp_path / run_id
    d.mkdir()
    m = {
        "n": n, "generated": _gen(**gen), "reference": _gen(mean_words=5.1),
        "length_ks": ks, "length_wasserstein": 0.5, "child_marker_gap": gap,
        "target_loss": {"loss": loss, "perplexity": 9.0},
        "run": {"run_id": run_id, "split": split, "bucket": bucket},
    }
    (d / "metrics.json").write_text(json.dumps(m))
    return d


def test_table_has_reference_row_and_one_row_per_run(tmp_path):
    runs = [_run(tmp_path, "a"), _run(tmp_path, "b")]
    t = compare.table(runs)
    assert "**real children**" in t
    assert "| a |" in t and "| b |" in t
    assert "bucket age5" in t


def test_table_skips_runs_without_metrics(tmp_path):
    pending = tmp_path / "pending"
    pending.mkdir()
    t = compare.table([_run(tmp_path, "a"), pending])
    assert "pending" not in t


def test_table_refuses_mixed_buckets(tmp_path):
    # The real-children row comes from one run; mixing buckets would show the wrong reference.
    runs = [_run(tmp_path, "a5"), _run(tmp_path, "a4", bucket="age4")]
    with pytest.raises(ValueError, match="bucket"):
        compare.table(runs)


def test_table_refuses_mixed_splits(tmp_path):
    runs = [_run(tmp_path, "v"), _run(tmp_path, "t", split="test")]
    with pytest.raises(ValueError, match="split"):
        compare.table(runs)


def test_delta_table_flags_only_differences_beyond_noise(tmp_path):
    local = _run(tmp_path, "local", gap=0.018, degen=0.005, loss=2.205)
    # marker gap moves by 0.010 (> 0.004 floor); degeneration by 0.2 pts (< 0.5 floor); loss identical
    hpg = _run(tmp_path, "local_hpg", gap=0.028, degen=0.007, loss=2.205)
    t = compare.delta_table([(local, hpg)])
    row = next(line for line in t.splitlines() if line.startswith("| local "))
    cells = [c.strip() for c in row.strip("|").split("|")]
    head = next(line for line in t.splitlines() if line.startswith("| Pair"))
    names = [c.strip() for c in head.strip("|").split("|")]
    gap_cell = cells[names.index("marker gap ↓")]
    degen_cell = cells[names.index("degen ↓")]
    loss_cell = cells[names.index("loss ↓")]
    assert compare.FLAG in gap_cell and "+0.010" in gap_cell
    assert compare.FLAG not in degen_cell
    assert compare.FLAG not in loss_cell


def test_delta_table_skips_pairs_with_missing_metrics(tmp_path):
    local = _run(tmp_path, "local")
    pending = tmp_path / "pending_hpg"
    pending.mkdir()
    t = compare.delta_table([(local, pending)])
    assert "pending_hpg" in t and "no metrics" in t


def test_delta_table_reference_row_shows_real_child_shift(tmp_path):
    a = _run(tmp_path, "age5_run")
    b = _run(tmp_path, "age4_run", bucket="age4")
    m = json.loads((b / "metrics.json").read_text())
    m["reference"]["mean_words"] = 4.1
    (b / "metrics.json").write_text(json.dumps(m))
    t = compare.delta_table([(a, b)], with_reference=True)
    row = next(line for line in t.splitlines() if line.startswith("| real children"))
    assert "5.10 → 4.10" in row
