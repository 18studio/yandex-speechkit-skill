#!/usr/bin/env python3
"""Helpers for Yandex Object Storage uploads and pre-signed URLs."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from env_config import load_project_env


load_project_env()


DEFAULT_ENDPOINT = "https://storage.yandexcloud.net"
DEFAULT_REGION = "ru-central1"
SERVICE = "s3"
ALGORITHM = "AWS4-HMAC-SHA256"
MAX_PRESIGN_TTL = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class StorageConfig:
    access_key: str
    secret_key: str
    bucket: str
    endpoint: str = DEFAULT_ENDPOINT
    region: str = DEFAULT_REGION


def load_storage_config(
    *,
    access_key: str | None = None,
    secret_key: str | None = None,
    bucket: str | None = None,
    endpoint: str | None = None,
    region: str | None = None,
) -> StorageConfig:
    resolved_access_key = (
        access_key
        or os.getenv("YANDEX_STORAGE_ACCESS_KEY")
        or os.getenv("ACCESS_KEY")
    )
    resolved_secret_key = (
        secret_key
        or os.getenv("YANDEX_STORAGE_SECRET_KEY")
        or os.getenv("SECRET_KEY")
    )
    resolved_bucket = bucket or os.getenv("YANDEX_STORAGE_BUCKET")
    resolved_endpoint = endpoint or os.getenv("YANDEX_STORAGE_ENDPOINT") or DEFAULT_ENDPOINT
    resolved_region = region or os.getenv("YANDEX_STORAGE_REGION") or DEFAULT_REGION

    if not resolved_access_key:
        raise SystemExit("No Object Storage access key provided. Use --access-key or YANDEX_STORAGE_ACCESS_KEY/ACCESS_KEY.")
    if not resolved_secret_key:
        raise SystemExit("No Object Storage secret key provided. Use --secret-key or YANDEX_STORAGE_SECRET_KEY/SECRET_KEY.")
    if not resolved_bucket:
        raise SystemExit("No Object Storage bucket provided. Use --bucket or YANDEX_STORAGE_BUCKET.")

    return StorageConfig(
        access_key=resolved_access_key,
        secret_key=resolved_secret_key,
        bucket=resolved_bucket,
        endpoint=resolved_endpoint.rstrip("/"),
        region=resolved_region,
    )


def guess_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def bucket_host(config: StorageConfig) -> str:
    parsed_endpoint = urllib.parse.urlparse(config.endpoint)
    return f"{config.bucket}.{parsed_endpoint.netloc}"


def object_url(config: StorageConfig, object_key: str) -> str:
    quoted_key = quote_object_key(object_key)
    parsed_endpoint = urllib.parse.urlparse(config.endpoint)
    return f"{parsed_endpoint.scheme}://{bucket_host(config)}/{quoted_key}"


def quote_object_key(object_key: str) -> str:
    normalized = object_key.lstrip("/")
    return urllib.parse.quote(normalized, safe="/-_.~")


def hash_payload(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def get_signing_key(secret_key: str, datestamp: str, region: str, service: str) -> bytes:
    k_date = sign(("AWS4" + secret_key).encode("utf-8"), datestamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def build_canonical_request(
    method: str,
    canonical_uri: str,
    canonical_querystring: str,
    canonical_headers: str,
    signed_headers: str,
    payload_hash: str,
) -> str:
    return "\n".join(
        [
            method,
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )


def build_string_to_sign(amz_date: str, credential_scope: str, canonical_request: str) -> str:
    canonical_request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    return "\n".join([ALGORITHM, amz_date, credential_scope, canonical_request_hash])


def upload_file(
    config: StorageConfig,
    file_path: Path,
    *,
    object_key: str,
    content_type: str | None = None,
) -> dict[str, str]:
    payload = file_path.read_bytes()
    payload_hash = hash_payload(payload)
    timestamp = now_utc()
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    datestamp = timestamp.strftime("%Y%m%d")
    credential_scope = f"{datestamp}/{config.region}/{SERVICE}/aws4_request"

    host = bucket_host(config)
    canonical_uri = f"/{quote_object_key(object_key)}"
    resolved_content_type = content_type or guess_content_type(file_path)
    headers = {
        "content-type": resolved_content_type,
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    canonical_request = build_canonical_request(
        "PUT",
        canonical_uri,
        "",
        canonical_headers,
        signed_headers,
        payload_hash,
    )
    string_to_sign = build_string_to_sign(amz_date, credential_scope, canonical_request)
    signing_key = get_signing_key(config.secret_key, datestamp, config.region, SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"{ALGORITHM} Credential={config.access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    request = urllib.request.Request(
        object_url(config, object_key),
        data=payload,
        method="PUT",
        headers={
            "Authorization": authorization,
            "Content-Type": resolved_content_type,
            "Host": host,
            "X-Amz-Content-SHA256": payload_hash,
            "X-Amz-Date": amz_date,
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            status = str(response.status)
            etag = response.headers.get("ETag", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f": {body}" if body else ""
        raise SystemExit(f"Object Storage upload failed with HTTP {exc.code} {exc.reason}{detail}") from exc

    return {
        "bucket": config.bucket,
        "endpoint": config.endpoint,
        "key": object_key,
        "url": object_url(config, object_key),
        "content_type": resolved_content_type,
        "etag": etag,
        "status": status,
    }


def presign_get_url(config: StorageConfig, object_key: str, *, expires_in: int = 3600) -> str:
    if expires_in <= 0:
        raise SystemExit("--expires-in must be greater than zero")
    if expires_in > MAX_PRESIGN_TTL:
        raise SystemExit(f"--expires-in must be <= {MAX_PRESIGN_TTL}")

    timestamp = now_utc()
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    datestamp = timestamp.strftime("%Y%m%d")
    credential_scope = f"{datestamp}/{config.region}/{SERVICE}/aws4_request"

    parsed_endpoint = urllib.parse.urlparse(config.endpoint)
    host = bucket_host(config)
    canonical_uri = f"/{quote_object_key(object_key)}"

    query = {
        "X-Amz-Algorithm": ALGORITHM,
        "X-Amz-Credential": f"{config.access_key}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_in),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_querystring = urllib.parse.urlencode(sorted(query.items()), quote_via=urllib.parse.quote, safe="-_.~")
    canonical_headers = f"host:{host}\n"
    canonical_request = build_canonical_request(
        "GET",
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        "host",
        "UNSIGNED-PAYLOAD",
    )
    string_to_sign = build_string_to_sign(amz_date, credential_scope, canonical_request)
    signing_key = get_signing_key(config.secret_key, datestamp, config.region, SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    signed_query = dict(query)
    signed_query["X-Amz-Signature"] = signature
    query_string = urllib.parse.urlencode(sorted(signed_query.items()), quote_via=urllib.parse.quote, safe="-_.~")
    return f"{parsed_endpoint.scheme}://{host}{canonical_uri}?{query_string}"
