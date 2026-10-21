"""Prepare adult-target CHAT examples from a local Gleason archive.

    python -m src.data.preprocess_adult --config configs/data_gleason_adult.yaml

Only counts and split IDs are written to the run summary. Transcript text is kept in the
git-ignored processed data directory and is never added to source control.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from src.data.build_examples import BuildConfig, build_turns, examples_from_turns
from src.data.parse_chat import Transcript, parse_text
from src.data.roles import ADULT_ROLES
from src.data.split import check_no_leakage, split_groups
from src.utils.config import load_config, resolve


def adult_speaker_codes(t: Transcript) -> set[str]:
    return {
        code
        for code, participant in t.participants.items()
        if participant.role in ADULT_ROLES
        or (participant.role != "Target_Child" and participant.age_months is not None and participant.age_months >= 216)
    }


def load_gleason(zip_path: Path, counters: Counter) -> list[tuple[str, Transcript]]:
    transcripts = []
    with ZipFile(zip_path) as archive:
        for entry in sorted(archive.infolist(), key=lambda item: item.filename):
            if entry.is_dir() or not entry.filename.lower().endswith(".cha"):
                continue
            counters["files_total"] += 1
            path = PurePosixPath(entry.filename)
            collection = path.parts[0] if len(path.parts) > 1 else "Gleason"
            raw = archive.read(entry).decode("utf-8", errors="replace")
            transcript = parse_text(raw, entry.filename, "Gleason", collection)
            if transcript.primary_language.lower() != "eng":
                counters["files_dropped_non_english"] += 1
                continue
            targets = transcript.target_children
            if not targets:
                counters["files_dropped_no_target_child"] += 1
                continue
            if len(targets) != 1:
                raise ValueError(f"Expected one target child in {entry.filename}, found {len(targets)}.")
            child_key = path.stem.casefold()
            child_id = f"Gleason/{child_key}"
            if not adult_speaker_codes(transcript):
                counters["files_dropped_no_adult_speaker"] += 1
                continue
            transcripts.append((child_id, transcript))
            counters["files_kept"] += 1
    return transcripts


def prepare(zip_path: Path, output_dir: Path, cfg: dict) -> dict:
    counters: Counter = Counter()
    transcripts = load_gleason(zip_path, counters)
    if not transcripts:
        raise ValueError(f"No eligible Gleason transcripts found in {zip_path}.")

    build_cfg = BuildConfig(
        context_turns=cfg.get("context_turns", 6),
        system_prompt=cfg.get(
            "system_prompt",
            "You are an adult conversation partner speaking with a young child. Respond naturally as the adult.",
        ),
    )
    examples_by_child: dict[str, list[dict]] = defaultdict(list)
    files_by_child: dict[str, set[str]] = defaultdict(set)
    adult_role_utterances: Counter = Counter()
    context_role_utterances: Counter = Counter()
    for child_id, transcript in transcripts:
        adult_codes = adult_speaker_codes(transcript)
        for utterance in transcript.utterances:
            if utterance.speaker in adult_codes:
                participant = transcript.participants[utterance.speaker]
                adult_role_utterances[participant.role or "Unknown"] += 1
            else:
                participant = transcript.participants.get(utterance.speaker)
                context_role_utterances[participant.role if participant and participant.role else "Unknown"] += 1

        turns, _ = build_turns(transcript, adult_codes, build_cfg, counters)
        examples = examples_from_turns(
            turns,
            build_cfg.system_prompt,
            build_cfg.context_turns,
            counters,
            target_label="adult",
        )
        files_by_child[child_id].add(transcript.path)
        collection = transcript.collection
        child_age = transcript.target_children[0].age_months
        for turn_index, messages in examples:
            examples_by_child[child_id].append({
                "id": f"{child_id}/{collection}:{turn_index}",
                "messages": messages,
                "meta": {
                    "child_id": child_id,
                    "corpus": "Gleason",
                    "collection": collection,
                    "age_months": child_age,
                    "turn_index": turn_index,
                },
            })

    examples_by_child = {child_id: rows for child_id, rows in examples_by_child.items() if rows}
    if len(examples_by_child) < 3:
        raise ValueError(
            "Need eligible adult-response examples from at least three children to create train/val/test splits."
        )

    split_cfg = cfg.get("split", {})
    fractions = tuple(split_cfg.get("fractions", (0.8, 0.1, 0.1)))
    if len(fractions) != 3 or any(value <= 0 for value in fractions) or abs(sum(fractions) - 1) > 1e-8:
        raise ValueError("split.fractions must contain three positive values that sum to 1.")
    child_groups = {child_id: child_id for child_id in examples_by_child}
    splits = split_groups(child_groups, fractions, split_cfg.get("seed", 42))
    if any(not splits[name] for name in ("train", "val", "test")):
        raise ValueError("The child count is too small for non-empty train/val/test splits.")
    check_no_leakage(splits, files_by_child)
    split_of = {child_id: name for name, child_ids in splits.items() for child_id in child_ids}

    rows_by_split: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    for child_id, rows in examples_by_child.items():
        for row in rows:
            row["meta"]["split"] = split_of[child_id]
            rows_by_split[split_of[child_id]].append(row)
    for rows in rows_by_split.values():
        rows.sort(key=lambda row: row["id"])

    output_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in rows_by_split.items():
        with (output_dir / f"{split}.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    split_manifest = {
        "seed": split_cfg.get("seed", 42),
        "fractions": fractions,
        **splits,
    }
    (output_dir / "splits.json").write_text(json.dumps(split_manifest, indent=2), encoding="utf-8")
    stats = {
        "source": zip_path.name,
        "filters": dict(counters),
        "children_by_split": {split: len(child_ids) for split, child_ids in splits.items()},
        "examples_by_split": {split: len(rows) for split, rows in rows_by_split.items()},
        "adult_role_utterances": dict(sorted(adult_role_utterances.items())),
        "context_role_utterances": dict(sorted(context_role_utterances.items())),
        "adult_roles_used": sorted(ADULT_ROLES),
    }
    (output_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/data_gleason_adult.yaml")
    parser.add_argument("--zip", default=None, help="override the local Gleason ZIP path")
    parser.add_argument("--output-dir", default=None, help="override the git-ignored output directory")
    args = parser.parse_args()

    cfg = load_config(resolve(args.config))
    zip_path = resolve(args.zip or cfg["zip_path"])
    output_dir = resolve(args.output_dir or Path(cfg["processed_dir"]) / cfg.get("output_name", "gleason_adult"))
    stats = prepare(zip_path, output_dir, cfg)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
