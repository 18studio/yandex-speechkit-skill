#!/usr/bin/env python3
"""Prepare, upload, pre-sign, and transcribe a local file with SpeechKit async STT v3."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from env_config import load_project_env
from object_storage import load_storage_config, object_url, presign_get_url, upload_file


load_project_env()


FORMAT_CONFIG = {
    "wav": {"suffix": ".wav", "container_audio_type": "WAV"},
    "ogg-opus": {"suffix": ".ogg", "container_audio_type": "OGG_OPUS"},
    "mp3": {"suffix": ".mp3", "container_audio_type": "MP3"},
}


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or f"Command failed: {' '.join(cmd)}"
        raise SystemExit(message)
    return proc.stdout


def load_async_module(base_dir: Path):
    module_path = base_dir / "speechkit_async_recognize_v3.py"
    spec = spec_from_file_location("speechkit_async_recognize_v3", module_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load module from {module_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", help="Source local media file")
    parser.add_argument("work_dir", help="Directory for prepared audio, raw results, and transcript")
    parser.add_argument("--bucket", help="Object Storage bucket name")
    parser.add_argument("--object-key", help="Object key inside the bucket")
    parser.add_argument(
        "--object-prefix",
        default=os.getenv("YANDEX_SPEECHKIT_OBJECT_PREFIX", "speechkit"),
        help="Prefix for auto-generated object keys",
    )
    parser.add_argument(
        "--format",
        choices=sorted(FORMAT_CONFIG),
        default=os.getenv("YANDEX_SPEECHKIT_ASYNC_FORMAT", "ogg-opus"),
        help="Prepared upload format",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=int(os.getenv("YANDEX_SPEECHKIT_SAMPLE_RATE", "16000")),
        help="Prepared audio sample rate in Hz",
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=int(os.getenv("YANDEX_SPEECHKIT_CHANNELS", "1")),
        help="Prepared audio channel count",
    )
    parser.add_argument(
        "--expires-in",
        type=int,
        default=int(os.getenv("YANDEX_SPEECHKIT_URL_TTL_SECONDS", str(24 * 60 * 60))),
        help="TTL for the private download URL",
    )
    parser.add_argument("--public-url", action="store_true", help="Use plain object URL instead of a private pre-signed URL")
    parser.add_argument("--keep-prepared", action="store_true", help="Keep the prepared audio file in work_dir")
    parser.add_argument(
        "--language-code",
        default=os.getenv("YANDEX_SPEECHKIT_LANGUAGE_CODE", "ru-RU"),
        help="SpeechKit language restriction",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("YANDEX_SPEECHKIT_MODEL", "general"),
        help="SpeechKit recognition model",
    )
    parser.add_argument("--folder-id", help="SpeechKit folder ID")
    parser.add_argument("--api-key", help="Yandex API key")
    parser.add_argument("--iam-token", help="Yandex IAM token")
    parser.add_argument("--access-key", help="Object Storage static access key")
    parser.add_argument("--secret-key", help="Object Storage static secret key")
    parser.add_argument("--endpoint", help="Object Storage endpoint, default: https://storage.yandexcloud.net")
    parser.add_argument("--region", help="Signing region, default: ru-central1")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--timeout", type=float, default=900.0, help="Maximum polling time in seconds")
    parser.add_argument("--raw-results", action="store_true", help="Keep raw result JSON and print transcript text")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    input_path = Path(args.input_file).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")

    work_dir = Path(args.work_dir).expanduser().resolve()
    prepared_dir = work_dir / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    config = FORMAT_CONFIG[args.format]
    prepared_path = prepared_dir / f"{input_path.stem}{config['suffix']}"

    prepare_cmd = [
        sys.executable,
        str(base_dir / "prepare_audio.py"),
        str(input_path),
        str(prepared_path),
        "--format",
        args.format,
        "--sample-rate",
        str(args.sample_rate),
        "--channels",
        str(args.channels),
        "--overwrite",
    ]
    run_text(prepare_cmd)

    storage_config = load_storage_config(
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket=args.bucket,
        endpoint=args.endpoint,
        region=args.region,
    )

    object_key = args.object_key
    if not object_key:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        object_key = f"{args.object_prefix.strip('/')}/{timestamp}_{input_path.stem}{prepared_path.suffix}"

    upload_meta = upload_file(storage_config, prepared_path, object_key=object_key)
    if args.public_url:
        source_url = object_url(storage_config, object_key)
    else:
        source_url = presign_get_url(storage_config, object_key, expires_in=args.expires_in)
    async_module = load_async_module(base_dir)
    auth_args = argparse.Namespace(
        api_key=args.api_key,
        iam_token=args.iam_token,
        folder_id=args.folder_id,
    )
    headers = async_module.build_headers(auth_args)
    body = {
        "uri": source_url,
        "recognition_model": {
            "model": args.model,
            "audio_format": {
                "container_audio": {
                    "container_audio_type": config["container_audio_type"],
                }
            },
        },
    }
    if args.language_code:
        body["recognition_model"]["language_restriction"] = {
            "restriction_type": "WHITELIST",
            "language_code": [args.language_code],
        }

    submitted = async_module.submit_recognition(headers=headers, body=body)
    operation_id = submitted.get("id")
    if not operation_id:
        raise SystemExit("Recognition request did not return an operation id.")
    operation = async_module.poll_operation(
        headers=headers,
        operation_id=str(operation_id),
        poll_interval=args.poll_interval,
        timeout=args.timeout,
    )
    result = async_module.fetch_result(headers=headers, operation_id=str(operation_id))
    transcript = async_module.extract_transcript(result).strip()

    transcript_path = work_dir / "transcript.txt"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(transcript + ("\n" if transcript else ""), encoding="utf-8")

    raw_result_path = work_dir / "result.json"
    raw_result_path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")

    manifest = {
        "source": str(input_path),
        "prepared_file": str(prepared_path),
        "bucket": storage_config.bucket,
        "object_key": object_key,
        "object_url": upload_meta["url"],
        "source_url": source_url,
        "private_source_url": not args.public_url,
        "speechkit_operation": submitted,
        "operation_status": operation,
        "transcript_path": str(transcript_path),
        "result_path": str(raw_result_path),
    }
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    if not args.keep_prepared and prepared_path.exists():
        prepared_path.unlink()
        try:
            prepared_dir.rmdir()
        except OSError:
            pass
        manifest["prepared_file_removed"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    if args.raw_results:
        print(json.dumps(manifest, indent=2, ensure_ascii=True))
    else:
        print(transcript)
    return 0


if __name__ == "__main__":
    sys.exit(main())
