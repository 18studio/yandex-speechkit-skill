# STT v3 Protocol Notes

Use this file when implementing gRPC clients or parsing STT v3 responses.

## Files in cloudapi

The main STT v3 proto files are:

- `yandex/cloud/ai/stt/v3/stt_service.proto`
- `yandex/cloud/ai/stt/v3/stt.proto`
- `yandex/cloud/ai/stt/v3/package_options.proto`

## Main Services

The service surface is centered around:

- `Recognizer.RecognizeStreaming` for bidirectional real-time recognition.
- `AsyncRecognizer.RecognizeFile` for async recognition of recorded files.
- `AsyncRecognizer.GetRecognition` for fetching async results.
- `AsyncRecognizer.DeleteRecognition` for deleting stored async results.

## Streaming Request Shape

For streaming recognition:

1. Open `RecognizeStreaming`.
2. Send a first message with `session_options`.
3. Send subsequent messages with one of:
   - `chunk` for raw audio bytes
   - `silence_chunk` for a known silence duration
   - `eou` when the client explicitly controls utterance boundaries

Do not send audio chunks before `session_options`.

## Streaming Response Shape

Handle these response variants explicitly:

- `partial`: intermediate hypothesis
- `final`: completed utterance result
- `eou_update`: end-of-utterance related update
- `final_refinement`: normalized final text
- `status_code`: service-side status signal
- `classifier_update`: classifier output
- `speaker_analysis`: speaker statistics
- `conversation_analysis`: dialog-level analysis
- `summarization`: summary output

When normalization is enabled, expect `final_refinement` after `final` instead of treating `final` as the only terminal text.

## Audio Formats

The protocol exposes these input formats:

- `LINEAR16_PCM`
- `WAV`
- `OGG_OPUS`
- `MP3`

If the application controls preprocessing, prefer using an explicitly validated format instead of guessing from the original file.

## Processing Modes and Models

Important protocol-level controls include:

- `REAL_TIME` and `FULL_DATA` processing modes
- streaming models such as `general` and `general:rc`
- deferred models for async recognition
- text normalization options
- language restriction options
- speaker labeling and speaker analysis
- conversation analysis
- summarization

Do not enable advanced analysis fields unless the product requirement needs them. They should not be part of the default transcription path.

## Practical Parsing Rule

Build transcript assembly around response type, not around arrival order alone:

- Use `partial` for transient UI.
- Use `final` for stable utterance boundaries.
- Replace or enrich with `final_refinement` when normalization is enabled.
- Keep analysis outputs separate from transcript text unless the caller explicitly wants them merged.
