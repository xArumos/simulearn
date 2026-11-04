import json
from zipfile import ZipFile

from src.data.parse_chat import parse_text
from src.data.preprocess_adult import adult_speaker_codes, prepare
from tests.fake_chat import FAKE


ADULT_CHAT = (
    FAKE.replace(
        "@Participants:\tMOT Mother, CHI Target_Child, ROB Robot, SIS Sister",
        "@Participants:\tMOT Mother, CHI Target_Child, ROB Robot, SIS Sister, INV Investigator",
    )
    .replace(
        "@ID:\teng|Fake|ROB|||||Other|||\n",
        "@ID:\teng|Fake|ROB|||||Other|||\n@ID:\teng|Fake|INV|||||Investigator|||\n",
    )
    .replace("@End", "*INV:\twe are going home .\n@End")
)


def test_adult_speakers_use_roles_not_all_non_child_speakers():
    transcript = parse_text(ADULT_CHAT, "Mother/child.cha", "Gleason", "Mother")

    assert adult_speaker_codes(transcript) == {"MOT", "INV"}


def test_prepare_creates_adult_targets_and_child_level_splits(tmp_path):
    zip_path = tmp_path / "Gleason.zip"
    output_dir = tmp_path / "processed"
    with ZipFile(zip_path, "w") as archive:
        for child_index in range(10):
            for collection in ("Mother", "Dinner"):
                archive.writestr(f"{collection}/child{child_index}.cha", ADULT_CHAT)

    stats = prepare(zip_path, output_dir, {
        "context_turns": 6,
        "split": {"fractions": [0.8, 0.1, 0.1], "seed": 42},
    })

    assert stats["children_by_split"] == {"train": 8, "val": 1, "test": 1}
    rows_by_split = {
        split: [json.loads(line) for line in (output_dir / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        for split in ("train", "val", "test")
    }
    split_by_child = {}
    adult_targets = set()
    for split, rows in rows_by_split.items():
        for row in rows:
            assert row["messages"][-1]["role"] == "assistant"
            assert row["messages"][-1]["content"] != "I said thank you."
            assert row["messages"][-1]["content"] != "no it's mine!"
            adult_targets.add(row["messages"][-1]["content"])
            assert split_by_child.setdefault(row["meta"]["child_id"], split) == split

    assert set(split_by_child) == {f"Gleason/child{i}" for i in range(10)}
    assert "we are going home." in adult_targets
    assert set(stats["adult_role_utterances"]) == {"Investigator", "Mother"}
    assert "Sister" in stats["context_role_utterances"]
    assert (output_dir / "stats.json").exists()
