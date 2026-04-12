# Gotchas

Use this file when debugging SpeechKit integrations or preparing implementation details.

## Authentication

- Requests require authentication with an IAM token or API key.
- Requests also commonly need a folder context.
- When authenticating as a service account, do not blindly include `folder_id` in requests; SpeechKit can use the folder where the service account was created.

## Streaming Session Rules

- Streaming is intended for real-time audio recognition.
- The first streaming message must be `session_options`.
- Send chunks at approximately real-time cadence.
- Do not let more than about 5 seconds pass between streaming messages.
- If the cadence or payload limits are violated, the session can terminate and must be recreated.

## Result Handling

- `partial` is not final text.
- `final` is not always the last useful text event when normalization is enabled.
- `final_refinement` may carry the cleaner final output.
- Large responses can exceed default gRPC client receive-message limits.

## Mode Selection Errors

Common integration mistake:

- Feeding long pre-recorded files into streaming because the team already built one streaming client.

Preferred correction:

- Use async recognition for long recorded files and reserve streaming for live audio.

## Audio Preparation

- Do not trust the file extension alone.
- Confirm actual codec and container before choosing request settings.
- Convert awkward source formats before calling the API.
- Keep timing fidelity when the user needs subtitles, timestamps, or diarization-like output.

## Advanced Features

STT v3 exposes more than plain transcription:

- classification
- speaker analysis
- conversation analysis
- summarization

Treat these as opt-in features. Do not mix them into a standard transcription flow unless the user asks for them.
