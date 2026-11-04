"""Demo logic that doesn't need a model: adapter discovery, prompts, context trimming, and the Space bundle."""
import importlib.util
from pathlib import Path

from src.demo.chat_demo import build_messages, find_adapters, render, system_prompt

ROOT = Path(__file__).resolve().parents[1]


def fake_adapter(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "adapter_config.json").write_text("{}")
    return folder


def test_only_ages_with_an_adapter_are_offered(tmp_path):
    a5 = fake_adapter(tmp_path / "run3" / "adapter")
    cfg = {"adapters": {4: {"path": str(tmp_path / "missing")}, 5: {"path": str(a5), "label": "run 3"}, 6: {"path": None}}}
    assert list(find_adapters(cfg)) == [5]
    assert find_adapters(cfg)[5]["label"] == "run 3"


def test_space_layout_uses_age_folders(tmp_path):
    fake_adapter(tmp_path / "age4")
    fake_adapter(tmp_path / "age6")
    cfg = {"adapters": {4: {"path": "ignored"}, 5: {"path": "ignored"}, 6: {"path": None}}}
    assert list(find_adapters(cfg, tmp_path)) == [4, 6]


def test_system_prompt_carries_the_age():
    assert system_prompt(4).startswith("You are a 4-year-old child talking with a caregiver.")
    assert "real 6-year-old" in system_prompt(6, strong=True)


def test_context_matches_training_window():
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(10)]
    msgs = build_messages("SYS", history, "new", context_turns=6)
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert [m["content"] for m in msgs[1:]] == ["5", "6", "7", "8", "9", "new"]  # 6 turns, the new adult line included
    assert len(build_messages("SYS", [], "hi", 6)) == 2


def test_silence_is_rendered_as_a_pause():
    assert render("<SILENCE FOR 3 SECONDS> um no") == "*(…pauses 3 s…)* um no"
    assert render("") == "*(no reply)*"


def test_space_bundle_has_code_and_no_data(tmp_path):
    spec = importlib.util.spec_from_file_location("build_space", ROOT / "scripts" / "build_space.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    files = {p.relative_to(tmp_path / "space").as_posix() for p in mod.build(tmp_path / "space")}
    assert {"app.py", "requirements.txt", "README.md", "configs/demo.yaml", "src/demo/chat_demo.py",
            "backend/app/main.py"} <= files
    assert not any(f.endswith((".cha", ".jsonl", ".safetensors")) or f.startswith("data/") for f in files)
