# Mode Selection

Use this file when you need to decide which SpeechKit STT path fits the request.

## Default Mapping

- Live microphone, assistant, bot, or broadcast captions: use streaming recognition.
- Short pre-recorded voice message: use synchronous recognition.
- Long recording, meeting, phone call, subtitles, or batch processing: use asynchronous recognition.

## Streaming

Use streaming when:

- Audio is produced in real time.
- The application benefits from intermediate recognition results.
- The system reacts immediately to final utterances.

Do not choose streaming just because the API is convenient. If the source is an existing file, streaming usually adds complexity without benefits.

## Synchronous

Use synchronous recognition when:

- The input is short.
- A simple request-response interaction is enough.
- The caller does not need async job handling.

Typical examples:

- Messenger voice notes.
- Short uploaded audio clips.
- Small utility commands that return text immediately.

## Asynchronous

Use asynchronous recognition when:

- The file is long or large.
- The job can complete out of band.
- The output may include timestamps, normalization, or follow-up processing.

Typical examples:

- Meeting transcription.
- Call-center recordings.
- Subtitle generation.
- Offline media processing pipelines.

## Decision Heuristics

- If the source is live, pick streaming.
- If the source is a file and the user wants immediate text for a short clip, consider synchronous.
- If the source is a file and the task sounds like batch transcription or media processing, pick asynchronous.
- If you are unsure between synchronous and asynchronous for a file workflow, prefer asynchronous because it is safer for longer jobs.
