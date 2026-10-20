"""Every config must load and point at things that exist, so a typo fails here, not on the GPU."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = sorted((ROOT / "configs").rglob("*.yaml"))


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: str(p.relative_to(ROOT)))
def test_config_loads(path):
    cfg = yaml.safe_load(path.read_text())
    assert isinstance(cfg, dict)
    if "model" in cfg:  # experiment config
        for key in ("run_name", "hypothesis", "age_label", "data", "eval"):
            assert key in cfg, f"{path.name}: missing {key}"
        data_cfg = next(c for c in [ROOT / "configs/data_all.yaml", ROOT / "configs/data_ctx10.yaml",
                                    ROOT / "configs/data_default.yaml"]
                        if yaml.safe_load(c.read_text())["processed_dir"] == cfg["data"]["processed_dir"])
        buckets = yaml.safe_load(data_cfg.read_text())["buckets"]
        for key in ("bucket", "eval_bucket"):
            if key in cfg["data"]:
                assert cfg["data"][key] in buckets, f"{path.name}: {key} {cfg['data'][key]} not in {data_cfg.name}"


def test_age6_configs_target_age6():
    for path in sorted((ROOT / "configs/age6").glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text())
        assert cfg["age_label"] == 6
        assert cfg["data"].get("eval_bucket", cfg["data"]["bucket"]) == "age6", path.name
