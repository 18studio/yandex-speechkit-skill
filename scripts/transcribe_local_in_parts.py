#!/usr/bin/env python3
"""Split a local audio file by size and transcribe each chunk with sync SpeechKit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


CONTAINER_FORMAT_MAP = {
    ".wav": "lpcm",
    ".mp3": "mp3",
    ".ogg": "oggopus",
    ".opus": "oggopus",
}


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"Command failed: {' '.join(cmd)}"
        raise SystemExit(message)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive CLI behavior
        raise SystemExit(f"Expected JSON output from command: {' '.join(cmd)}") from exc


def detect_sync_format(path: Path, explicit_format: str | None) -> str | None:
    if explicit_format:
        return explicit_format
    return CONTAINER_FORMAT_MAP.get(path.suffix.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", help="Source audio file to split and transcribe")
    parser.add_argument("work_dir", help="Directory where chunks and results will be written")
    parser.add_argument("--max-bytes", type=int, help="Maximum size of each chunk in bytes")
    parser.add_argument("--max-size-mb", type=float, help="Maximum size of each chunk in MiB")
    parser.add_argument("--margin", type=float, default=0.97, help="Safety multiplier for chunk size")
    parser.add_argument("--min-segment-seconds", type=float, default=1.0, help="Minimum recursive split size")
    parser.add_argument("--lang", default="ru-RU", help="Recognition language")
    parser.add_argument("--topic", default="general", help="Recognition model/topic")
    parser.add_argument("--folder-id", help="Folder ID when required by your auth flow")
    parser.add_argument("--format", dest="audio_format", help="SpeechKit sync format parameter, e.g. lpcm")
    parser.add_argument("--sample-rate-hertz", type=int, help="Sample rate query parameter")
    parser.add_argument("--profanity-filter", action="store_true", help="Enable profanity filter")
    parser.add_argument("--api-key", help="Yandex API key")
    parser.add_argument("--iam-token", help="Yandex IAM token")
    parser.add_argument("--prefix", default=None, help="Optional prefix for generated chunk names")
    parser.add_argument("--dry-run", action="store_true", help="Only split and prepare manifest without API calls")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    work_dir = Path(args.work_dir).expanduser().resolve()
    chunks_dir = work_dir / "chunks"
    results_dir = work_dir / "results"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    split_cmd = [
        sys.executable,
        str(base_dir / "split_audio_by_size.py"),
        str(input_path),
        str(chunks_dir),
        "--margin",
        str(args.margin),
        "--min-segment-seconds",
        str(args.min_segment_seconds),
    ]
    if args.max_bytes is not None:
        split_cmd.extend(["--max-bytes", str(args.max_bytes)])
    if args.max_size_mb is not None:
        split_cmd.extend(["--max-size-mb", str(args.max_size_mb)])
    if args.prefix:
        split_cmd.extend(["--prefix", args.prefix])

    split_manifest = run_json(split_cmd)
    parts = split_manifest.get("parts") or []
    if not isinstance(parts, list) or not parts:
        raise SystemExit("Split step did not produce any chunks")

    final_parts: list[dict[str, object]] = []
    transcript_blocks: list[str] = []

    for index, part in enumerate(parts, start=1):
        if not isinstance(part, dict) or "path" not in part:
            raise SystemExit("Split manifest contains an invalid part entry")
        part_path = Path(str(part["path"]))
        transcript_path = results_dir / f"part{index:03d}.txt"

        entry: dict[str, object] = {
            "index": index,
            "path": str(part_path),
            "start_seconds": part.get("start_seconds"),
            "duration_seconds": part.get("duration_seconds"),
            "size_bytes": part.get("size_bytes"),
            "transcript_path": str(transcript_path),
        }

        if args.dry_run:
            entry["status"] = "dry-run"
            final_parts.append(entry)
            continue

        recognize_cmd = [
            sys.executable,
            str(base_dir / "speechkit_sync_recognize.py"),
            str(part_path),
            "--lang",
            args.lang,
            "--topic",
            args.topic,
        ]
        if args.folder_id:
            recognize_cmd.extend(["--folder-id", args.folder_id])

        detected_format = detect_sync_format(part_path, args.audio_format)
        if detected_format:
            recognize_cmd.extend(["--format", detected_format])
        if args.sample_rate_hertz is not None:
            recognize_cmd.extend(["--sample-rate-hertz", str(args.sample_rate_hertz)])
        if args.profanity_filter:
            recognize_cmd.append("--profanity-filter")
        if args.api_key:
            recognize_cmd.extend(["--api-key", args.api_key])
        if args.iam_token:
            recognize_cmd.extend(["--iam-token", args.iam_token])

        proc = subprocess.run(recognize_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            entry["status"] = "error"
            entry["error"] = proc.stderr.strip() or proc.stdout.strip() or "Unknown recognition error"
            final_parts.append(entry)
            break

        transcript = proc.stdout.strip()
        transcript_path.write_text(transcript + ("\n" if transcript else ""), encoding="utf-8")
        entry["status"] = "ok"
        entry["text"] = transcript
        final_parts.append(entry)
        transcript_blocks.append(transcript)

    overall_status = "ok"
    if any(part.get("status") == "error" for part in final_parts):
        overall_status = "error"
    elif args.dry_run:
        overall_status = "dry-run"

    transcript_path = work_dir / "transcript.txt"
    if transcript_blocks:
        transcript_path.write_text("\n\n".join(block for block in transcript_blocks if block), encoding="utf-8")

    manifest = {
        "source": str(input_path),
        "status": overall_status,
        "chunking": split_manifest,
        "parts": final_parts,
        "transcript_path": str(transcript_path),
    }
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=True))
    return 0 if overall_status != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
