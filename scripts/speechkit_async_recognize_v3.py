#!/usr/bin/env python3
"""Submit, poll, and fetch Yandex SpeechKit STT v3 async recognition."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


SUBMIT_ENDPOINT = "https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync"
RESULT_ENDPOINT = "https://stt.api.cloud.yandex.net/stt/v3/getRecognition"
OPERATION_ENDPOINT = "https://operation.api.cloud.yandex.net/operations"


def build_auth_header(args: argparse.Namespace) -> str:
    if args.api_key:
        return f"Api-Key {args.api_key}"
    if args.iam_token:
        return f"Bearer {args.iam_token}"
    env_api_key = os.getenv("YANDEX_API_KEY") or os.getenv("API_KEY")
    if env_api_key:
        return f"Api-Key {env_api_key}"
    env_iam = os.getenv("YANDEX_IAM_TOKEN") or os.getenv("IAM_TOKEN")
    if env_iam:
        return f"Bearer {env_iam}"
    raise SystemExit("No API key or IAM token provided. Use flags or env vars.")


def build_headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {
        "Authorization": build_auth_header(args),
        "Content-Type": "application/json",
    }
    if args.folder_id:
        headers["x-folder-id"] = args.folder_id
    return headers


def format_request_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f": {body}" if body else ""
        return f"SpeechKit request failed with HTTP {exc.code} {exc.reason}{detail}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            return (
                "SpeechKit request failed due to TLS certificate verification. "
                "Your local Python trust store appears incomplete."
            )
        return f"SpeechKit request failed: {reason}"
    return f"SpeechKit request failed: {exc}"


def request_json(url: str, *, headers: dict[str, str], body: dict | None = None, method: str = "GET") -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise SystemExit(format_request_error(exc)) from exc


def build_request_body(args: argparse.Namespace) -> dict:
    body: dict[str, object] = {
        "uri": args.uri,
        "recognition_model": {
            "model": args.model,
            "audio_format": {
                "container_audio": {
                    "container_audio_type": args.container_audio_type,
                }
            },
        },
    }
    if args.language_code:
        body["recognition_model"]["language_restriction"] = {
            "restriction_type": "WHITELIST",
            "language_code": [args.language_code],
        }
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", required=True, help="Object Storage HTTPS URL to the audio file")
    parser.add_argument("--model", default="general", help="Recognition model")
    parser.add_argument(
        "--container-audio-type",
        default="WAV",
        choices=["WAV", "OGG_OPUS", "MP3"],
        help="Container type for recognition_model.audio_format.container_audio.container_audio_type",
    )
    parser.add_argument("--language-code", help="Optional single language code for whitelist restriction")
    parser.add_argument("--folder-id", help="Folder ID. Recommended for service-account flows.")
    parser.add_argument("--api-key", help="Yandex API key")
    parser.add_argument("--iam-token", help="Yandex IAM token")
    parser.add_argument("--poll", action="store_true", help="Poll until the operation is done")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--timeout", type=float, default=900.0, help="Maximum polling time in seconds")
    parser.add_argument("--raw-results", action="store_true", help="Print full result JSON")
    args = parser.parse_args()

    headers = build_headers(args)
    submit_body = build_request_body(args)
    operation = request_json(SUBMIT_ENDPOINT, headers=headers, body=submit_body, method="POST")
    print(json.dumps({"submitted": operation}, indent=2, ensure_ascii=True))

    operation_id = operation.get("id")
    if not args.poll:
        return 0
    if not operation_id:
        raise SystemExit("Recognition request did not return an operation id.")

    deadline = time.monotonic() + args.timeout
    while True:
        op = request_json(f"{OPERATION_ENDPOINT}/{urllib.parse.quote(str(operation_id))}", headers=headers)
        done = bool(op.get("done"))
        print(json.dumps({"operation": op}, indent=2, ensure_ascii=True))
        if done:
            break
        if time.monotonic() >= deadline:
            raise SystemExit("Timed out while waiting for async recognition.")
        time.sleep(args.poll_interval)

    result = request_json(
        f"{RESULT_ENDPOINT}?{urllib.parse.urlencode({'operation_id': str(operation_id)})}",
        headers=headers,
    )
    if args.raw_results:
        print(json.dumps({"result": result}, indent=2, ensure_ascii=True))
    else:
        alternatives = (((result.get("result") or {}).get("final") or {}).get("alternatives") or [])
        text = "\n".join(alt.get("text", "") for alt in alternatives if isinstance(alt, dict))
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
