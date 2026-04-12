# Yandex SpeechKit Scripts

Small command-line utilities for preparing audio and running speech recognition with Yandex SpeechKit.

## Files

- `inspect_audio.py` inspects a local audio file and prints a JSON summary with a SpeechKit usage recommendation.
- `prepare_audio.py` converts source media into SpeechKit-friendly formats with `ffmpeg`.
- `split_audio_by_size.py` splits a local audio file into chunks under a target file size.
- `speechkit_sync_recognize.py` sends a local audio file to the synchronous SpeechKit STT REST endpoint.
- `speechkit_async_recognize_v3.py` submits an Object Storage file URL to the async SpeechKit STT v3 API and can poll until completion.
- `transcribe_local_in_parts.py` splits a large local file and transcribes each chunk through the synchronous SpeechKit endpoint.

## Requirements

- Python 3.11+
- `ffmpeg` for audio conversion
- `ffprobe` for richer audio inspection output
- Yandex Cloud credentials:
  - `YANDEX_API_KEY` or `API_KEY`
  - `YANDEX_IAM_TOKEN` or `IAM_TOKEN`

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

Run async v3 recognition for an Object Storage URL:

```bash
export YANDEX_IAM_TOKEN=your_iam_token
python3 speechkit_async_recognize_v3.py \
  --uri "https://storage.yandexcloud.net/bucket/path/audio.wav" \
  --container-audio-type WAV \
  --language-code ru-RU \
  --poll
```

## Notes

- The synchronous API expects local file bytes and is suitable for shorter requests.
- The async v3 flow expects a remote object URL and is better for longer recordings.
- `prepare_audio.py` currently supports `wav`, `linear16`, `ogg-opus`, and `mp3` output presets.
- `split_audio_by_size.py` keeps the original codec/container and uses `ffmpeg` stream copy where possible.
- If a chunk still exceeds the size limit because of container boundaries or variable bitrate, the script recursively splits that chunk again.
- `transcribe_local_in_parts.py` stores chunks in `work_dir/chunks`, per-part text in `work_dir/results`, the merged transcript in `work_dir/transcript.txt`, and a full run manifest in `work_dir/manifest.json`.

## License

MIT. See [LICENSE](./LICENSE).
