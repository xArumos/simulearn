"""Demo logic that doesn't need a model: adapter discovery, prompts, context trimming, and the Space bundle."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import peft
import pytest

from src.demo import chat_demo, engine
from src.demo.chat_demo import Demo, build_messages, find_adapters, render, system_prompt

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
            "src/demo/engine.py", "src/utils/chat_template.py", "src/utils/model_policy.py", "backend/app/main.py"} <= files
    assert not any(f.endswith((".cha", ".jsonl", ".safetensors")) or f.startswith("data/") for f in files)


def test_engine_does_not_import_gradio():
    """The product backend loads the model through src.demo.engine and must not pull in the Gradio UI."""
    code = "import sys, src.demo.engine; assert 'gradio' not in sys.modules, 'gradio was imported'"
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_chat_demo_reexports_the_engine():
    """space/app.py, scripts/upload_adapters.sh and older code import these names from chat_demo."""
    for name in ("Demo", "build_messages", "system_prompt", "render", "find_adapters", "check_4bit", "pick_device",
                 "SILENCE_RE", "timed"):
        assert getattr(chat_demo, name) is getattr(engine, name)


class FakePeft:
    """Stands in for peft.PeftModel: records how adapters are loaded and whether the model is moved."""
    calls: list = []

    def __init__(self, base):
        self.base, self.moved_to = base, None

    @classmethod
    def from_pretrained(cls, base, path, adapter_name, **kw):
        cls.calls.append(("from_pretrained", adapter_name, kw.get("torch_device")))
        return cls(base)

    def load_adapter(self, path, adapter_name, **kw):
        FakePeft.calls.append(("load_adapter", adapter_name, kw.get("torch_device")))

    def to(self, device):
        if self.base.get("load_in_4bit"):
            raise AssertionError("bitsandbytes 4-bit models can't be moved with .to()")
        self.moved_to = device
        return self

    def eval(self):
        return self


@pytest.fixture
def fake_loading(monkeypatch):
    """Mock the model, tokenizer and PEFT loaders (no download, no GPU). Returns the configs passed to load_model."""
    loaded = []
    FakePeft.calls = []
    monkeypatch.delenv("SPACES_ZERO_GPU", raising=False)
    monkeypatch.setattr(engine, "load_tokenizer", lambda name: object())
    monkeypatch.setattr(engine, "load_model", lambda mcfg: loaded.append(mcfg) or dict(mcfg))
    monkeypatch.setattr(peft, "PeftModel", FakePeft)
    return loaded


def demo_cfg(**extra):
    return {"base_model": "fake/base", "context_turns": 6, "decoding": {}, **extra}


ADAPTERS = {4: {"path": Path("a4"), "label": ""}, 5: {"path": Path("a5"), "label": ""}}


def test_bf16_path_is_unchanged(fake_loading):
    demo = Demo(demo_cfg(), ADAPTERS, device="cuda")
    assert fake_loading == [{"name": "fake/base", "dtype": "bfloat16", "device_map": "cpu"}]
    assert FakePeft.calls == [("from_pretrained", "age4", "cpu"), ("load_adapter", "age5", "cpu")]
    assert demo.model.moved_to == "cuda"


def test_load_in_4bit_false_is_the_bf16_path(fake_loading):
    Demo(demo_cfg(load_in_4bit=False), ADAPTERS, device="cuda")
    assert "load_in_4bit" not in fake_loading[0]


def test_4bit_loads_straight_onto_cuda(fake_loading):
    demo = Demo(demo_cfg(load_in_4bit=True), ADAPTERS, device="cuda")
    assert fake_loading == [{"name": "fake/base", "dtype": "bfloat16", "device_map": "cuda", "load_in_4bit": True}]
    assert FakePeft.calls == [("from_pretrained", "age4", "cuda"), ("load_adapter", "age5", "cuda")]
    assert demo.model.moved_to is None  # never .to(): FakePeft.to raises for a 4-bit base


def test_4bit_on_cpu_is_refused(fake_loading):
    with pytest.raises(SystemExit, match="4-bit.*CUDA GPU"):
        Demo(demo_cfg(load_in_4bit=True), ADAPTERS, device="cpu")
    assert fake_loading == []


def test_4bit_on_zerogpu_is_refused(fake_loading, monkeypatch):
    monkeypatch.setenv("SPACES_ZERO_GPU", "true")
    with pytest.raises(SystemExit, match="ZeroGPU"):
        Demo(demo_cfg(load_in_4bit=True), ADAPTERS, device="cuda")
    assert fake_loading == []
