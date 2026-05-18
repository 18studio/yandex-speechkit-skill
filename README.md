# Yandex SpeechKit Scripts

Small command-line utilities for preparing audio and running speech recognition with Yandex SpeechKit.

## Files

- `.env` stores local project defaults for SpeechKit and Object Storage credentials/settings.
- `inspect_audio.py` inspects a local audio file and prints a JSON summary with a SpeechKit usage recommendation.
- `object_storage_upload.py` uploads a local file to Yandex Object Storage using the S3-compatible API.
- `object_storage_presign.py` generates a private pre-signed download URL for an uploaded object.
- `prepare_audio.py` converts source media into SpeechKit-friendly formats with `ffmpeg`.
- `split_audio_by_size.py` splits a local audio file into chunks under a target file size.
- `speechkit_sync_recognize.py` sends a local audio file to the synchronous SpeechKit STT REST endpoint.
- `speechkit_async_recognize_v3.py` submits an Object Storage file URL to the async SpeechKit STT v3 API and can poll until completion.
- `transcribe_file_async.py` prepares a local file, uploads it to Object Storage, creates a private URL, and runs async recognition.
- `transcribe_local_in_parts.py` splits a large local file and transcribes each chunk through the synchronous SpeechKit endpoint.

## Requirements

- Python 3.11+
- `ffmpeg` for audio conversion
- `ffprobe` for richer audio inspection output
- Yandex Cloud credentials:
  - `YANDEX_IAM_TOKEN` or `IAM_TOKEN`
  - `YANDEX_API_KEY` or `API_KEY` as fallback
- Yandex Object Storage static access credentials in `.env` or process env:
  - `YANDEX_STORAGE_ACCESS_KEY` or `ACCESS_KEY`
  - `YANDEX_STORAGE_SECRET_KEY` or `SECRET_KEY`
  - `YANDEX_STORAGE_BUCKET`

SpeechKit and Object Storage credentials are separate concerns. SpeechKit requests use `YANDEX_IAM_TOKEN` first and fall back to `YANDEX_API_KEY`; Object Storage uploads in these scripts use S3-compatible static keys. A key that can upload to a bucket does not imply permission to call SpeechKit, and a SpeechKit IAM token does not replace Object Storage static keys for the signed upload path.

## Quick Start

Inspect a file:

```bash
python3 inspect_audio.py ./audio.wav
```

Convert audio to mono 16 kHz WAV:

```bash
python3 prepare_audio.py ./input.mp3 ./output.wav --format wav --sample-rate 16000 --channels 1
```

Split a large recording into chunks smaller than 20 MiB:

```bash
python3 split_audio_by_size.py ./meeting.mp3 ./chunks --max-size-mb 20
```

Split a large local file and transcribe each chunk:

```bash
export YANDEX_API_KEY=your_api_key
python3 transcribe_local_in_parts.py ./meeting.mp3 ./meeting_workdir --max-size-mb 20 --lang ru-RU
```

Run synchronous recognition for a local file:

```bash
export YANDEX_API_KEY=your_api_key
python3 speechkit_sync_recognize.py ./output.wav --lang ru-RU --topic general
```

Upload a file to Object Storage:

```bash
python3 object_storage_upload.py ./meeting.ogg --object-key speechkit/meeting.ogg
```

Create a private download URL:

```bash
python3 object_storage_presign.py --object-key speechkit/meeting.ogg --expires-in 86400
```

Run async v3 recognition for an Object Storage URL:

```bash
export YANDEX_IAM_TOKEN=your_iam_token
python3 speechkit_async_recognize_v3.py \
  --uri "https://storage.yandexcloud.net/bucket/path/audio.wav" \
  --container-audio-type WAV \
  --language-code ru-RU \
  --poll
```

Run the full async local-file pipeline:

```bash
python3 transcribe_file_async.py ./meeting.mp4 ./meeting_async_workdir
```

Resume the async pipeline after a failed upload or SpeechKit request:

```bash
python3 transcribe_file_async.py ./meeting.mp4 ./meeting_async_workdir \
  --prepared-file ./meeting_async_workdir/prepared/meeting.ogg \
  --skip-prepare
```

Resume without re-uploading when you already have a readable object URL:

```bash
python3 transcribe_file_async.py ./meeting.mp4 ./meeting_async_workdir \
  --skip-prepare \
  --skip-upload \
  --source-url "https://bucket.storage.yandexcloud.net/speechkit/meeting.ogg?..."
```

Resume from an already submitted operation:

```bash
python3 transcribe_file_async.py ./meeting_async_workdir --operation-id <operation_id>
```

Run the async pipeline as separate steps:

```bash
python3 prepare_audio.py ./meeting.mp4 ./meeting_async_workdir/prepared/meeting.ogg \
  --format ogg-opus --sample-rate 16000 --channels 1 --overwrite

python3 object_storage_upload.py ./meeting_async_workdir/prepared/meeting.ogg \
  --object-key speechkit/meeting.ogg

python3 object_storage_presign.py --object-key speechkit/meeting.ogg --expires-in 86400

python3 speechkit_async_recognize_v3.py \
  --uri "<presigned_get_url>" \
  --container-audio-type OGG_OPUS \
  --language-code ru-RU

python3 speechkit_async_recognize_v3.py --operation-id <operation_id> --poll

python3 speechkit_async_recognize_v3.py \
  --operation-id <operation_id> \
  --fetch-only \
  --result-file ./meeting_async_workdir/result.json \
  --transcript-file ./meeting_async_workdir/transcript.txt
```

## Notes

- The synchronous API expects local file bytes and is suitable for shorter requests.
- The async v3 flow expects a remote object URL and is better for longer recordings.
- After recognition, template-based analysis should be saved as a separate derivative file, not mixed into the raw transcript. For example, use a UX scenario prompt to extract user context, goals, path, expectations, friction, success criteria, and recommendations from the transcript.
- If Object Storage settings are present in `.env` or process env, this project should always use the async path for file transcription.
- The recommended async path in this repo is: local file -> `prepare_audio.py` -> `object_storage_upload.py` -> `object_storage_presign.py` -> `speechkit_async_recognize_v3.py`.
- `transcribe_file_async.py` keeps prepared audio by default so retries can reuse it with `--prepared-file` and `--skip-prepare`.
- Object Storage upload retries transient network failures, streams the file instead of loading it into memory, uses an explicit timeout, and falls back to `curl` including a presigned PUT attempt.
- `prepare_audio.py` currently supports `wav`, `linear16`, `ogg-opus`, and `mp3` output presets.
- When the source file contains video, `prepare_audio.py` now maps only the first audio stream and explicitly drops non-audio streams before conversion.
- `split_audio_by_size.py` keeps the original codec/container and uses `ffmpeg` stream copy where possible.
- If a chunk still exceeds the size limit because of container boundaries or variable bitrate, the script recursively splits that chunk again.
- `speechkit_sync_recognize.py`, `speechkit_async_recognize_v3.py`, and `transcribe_file_async.py` load defaults from `.env` automatically.
- `transcribe_local_in_parts.py` now refuses to run when Object Storage env is configured, to enforce async mode at the orchestration level.
- `transcribe_local_in_parts.py` converts chunks to raw LINEAR16 (`s16le`) before sync recognition, sends them with `--format lpcm --sample-rate-hertz 16000`, retries transient sync failures, and supports `--resume`.
- `transcribe_local_in_parts.py` stores chunks in `work_dir/chunks`, raw LINEAR16 chunks in `work_dir/raw_chunks`, per-part text in `work_dir/results`, the merged transcript in `work_dir/transcript.txt`, and a full run manifest in `work_dir/manifest.json`.

## License

MIT. See [LICENSE](./LICENSE).
