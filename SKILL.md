---
name: yandex-speechkit
description: Work with Yandex SpeechKit speech-to-text, especially STT v3 over gRPC. Use when Codex needs to choose between streaming, synchronous, or asynchronous recognition; prepare audio for SpeechKit; generate or write clients from the cloudapi proto files; configure STT v3 request options; troubleshoot authentication, folder ID, format, or session issues; or post-process SpeechKit transcripts into plain text, timestamps, subtitles, or structured output.
---

# Yandex SpeechKit

## Overview

Use this skill to implement or troubleshoot speech recognition with Yandex SpeechKit. Default to STT v3 for new gRPC integrations and choose the recognition mode based on whether audio is live, short and pre-recorded, or long and pre-recorded.

## Workflow Decision

Choose the recognition mode before writing code:

- Use streaming recognition for live microphone audio, assistants, bots, and real-time captions.
- Use synchronous recognition for short pre-recorded voice messages when a single request-response flow is enough.
- Use asynchronous recognition for long recordings, meetings, calls, subtitles, and other offline transcription jobs.

If the task starts from a recorded file, do not force it through streaming unless the user explicitly needs real-time emulation.

Read [references/mode-selection.md](references/mode-selection.md) when the mode is not obvious.

## Default Choices

- Prefer API v3 for new projects.
- Prefer gRPC clients generated from `yandex/cloud/ai/stt/v3/stt_service.proto`.
- Prefer service-account authentication when possible.
- Prefer explicit audio preparation over guessing server-side behavior.
- Prefer handling `partial`, `final`, and `final_refinement` separately in streaming clients.
- Prefer asynchronous recognition for long files and batch workflows.

## Streaming STT v3

When implementing streaming recognition:

1. Generate or use a client for `Recognizer.RecognizeStreaming`.
2. Send `session_options` as the first client message.
3. Stream audio chunks after the session is configured.
4. Keep chunk cadence close to real time.
5. Stop or reconnect if the session hits timing or payload limits.
6. Accumulate `partial` results for UI feedback and `final` or `final_refinement` for committed transcript text.

Use `silence_chunk` when the client already knows the silence duration and wants to avoid transmitting literal silence bytes. Use explicit `eou` controls only when the application owns utterance boundary detection.

Read [references/stt-v3-protocol.md](references/stt-v3-protocol.md) before implementing request and response handling.

## File Recognition

For recorded audio files:

1. Decide whether the file is short enough for synchronous recognition or should go through async recognition.
2. Normalize the input audio format before sending it.
3. Submit the recognition request with explicit settings instead of relying on defaults.
4. Poll or fetch the final result for async operations.
5. Convert the result into the user's requested shape: plain transcript, timed words, subtitles, speaker-separated text, or structured JSON.

When the user asks for subtitles, meeting notes, or call transcripts, assume asynchronous recognition is the default unless there is a strong reason not to.

## Audio Preparation

Before sending audio:

- Identify whether the source is live audio or a file.
- Confirm the container and codec instead of inferring from the file extension.
- Convert unsupported or inconvenient inputs before calling SpeechKit.
- Preserve channel and timing information when the requested output depends on it.

Use the bundled scripts when helpful:

- `scripts/inspect_audio.py` to inspect codec, sample rate, channels, duration, and a recommended SpeechKit path.
- `scripts/prepare_audio.py` to convert inputs with `ffmpeg` into WAV, LINEAR16, OGG Opus, or MP3.
- `scripts/split_audio_by_size.py` to break large local recordings into chunks under a maximum file size before upload or batch processing.
- `scripts/transcribe_local_in_parts.py` to split a large local recording and run synchronous recognition over each chunk when you want to stay entirely on local files.

If you need protocol-level format guidance or common conversion pitfalls, read [references/gotchas.md](references/gotchas.md).

## Recognition Options

Adjust recognition options only when the task needs them:

- Enable normalization when the user needs cleaner final text.
- Keep raw recognition behavior when downstream code needs the original surface form.
- Configure language restrictions only when the domain is narrow enough to benefit from them.
- Enable speaker or conversation analysis only when the output actually needs it.
- Use summarization only when the workflow explicitly asks for summary output from the transcript pipeline.

Avoid turning on every advanced option by default. Start with the smallest settings set that satisfies the request.

## Validation Loop

For any non-trivial integration:

1. Validate authentication first.
2. Validate audio format second.
3. Validate the selected recognition mode third.
4. Validate response parsing against real `partial` and `final` payloads.
5. Re-run with a short known-good audio sample before debugging large inputs.

If behavior is unclear, inspect the exact request and response shape before changing model or audio settings.

Useful command starters:

- `python scripts/inspect_audio.py path/to/file`
- `python scripts/prepare_audio.py input.m4a output.wav --format wav --sample-rate 16000 --channels 1`
- `python scripts/split_audio_by_size.py meeting.mp3 chunks/ --max-size-mb 20`
- `python scripts/transcribe_local_in_parts.py meeting.mp3 workdir/ --max-size-mb 20 --lang ru-RU`
- `python scripts/speechkit_sync_recognize.py file.wav --folder-id <folder-id> --format lpcm --sample-rate-hertz 16000`
- `python scripts/speechkit_async_recognize_v3.py --uri https://storage.yandexcloud.net/.../file.wav --folder-id <folder-id> --poll`

## Gotchas

- Service-account authentication and folder handling behave differently from user-token flows; do not blindly send `folder_id` in every request.
- Streaming is for real-time audio. For recorded files, synchronous or asynchronous modes are usually the correct choice.
- In streaming mode, the first message must configure the session before audio chunks are sent.
- If the client stops sending messages for too long, the streaming session is terminated.
- `final_refinement` is a separate response type and may arrive after `final` when normalization is enabled.
- Large gRPC results can exceed default client receive-size limits.
- The protocol exposes advanced analysis features; do not wire them into the default path unless the user asks for them.

Read [references/gotchas.md](references/gotchas.md) when debugging failures or inconsistent output.

## Output Shapes

Default to the smallest useful output:

- Plain text transcript for simple transcription requests.
- Segment timestamps when the user asks for subtitle-like output.
- Word timings only when explicitly needed.
- Structured JSON when the result feeds another system.
- Speaker-separated output only when speaker labeling or analysis is enabled.

State any assumptions about normalization, timestamps, and speaker separation in the final result.
