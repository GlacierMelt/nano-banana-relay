---
name: nano-banana-relay
description: Generate and edit raster images through the draw.hugusir.top OpenAI-compatible relay using Nano Banana2, Nano Banana Pro, gemini-2.5-flash-image, and other exposed image models. Use when Codex needs text-to-image, image-to-image, multi-reference editing, synchronous or asynchronous image jobs, model discovery, status polling, or downloading results from the Nano Banana relay API.
---

# Nano Banana Relay

Use the bundled CLI for deterministic requests and result handling. Resolve paths relative to this `SKILL.md` file.

## Setup

1. Set the API key only in the current process environment:

   ```bash
   export NANO_BANANA_API_KEY="YOUR_API_KEY"
   ```

2. Keep the default endpoint unless the user provides another compatible relay:

   ```bash
   export NANO_BANANA_BASE_URL="https://draw.hugusir.top/api/v1"
   ```

3. Never write, print, commit, or embed the API key in generated files. Prefer a process-scoped environment variable when the user supplies a key in chat.

## Choose A Workflow

- Use `generate` for synchronous text-to-image.
- Use `edit` for one or more reference images. The API accepts at most 8 references totaling 40 MB.
- Use `generate --async` to submit a background text-to-image job.
- Add `--wait` to submit, poll, and download in one command.
- Use `status` for one status check or `wait` to resume polling an existing job.
- Use `models` when the requested model name is uncertain or before relying on a model-specific capability.

## Run Commands

Set `CLIENT` to the absolute path of `scripts/nano_banana.py` inside this skill before running commands.

List current models:

```bash
python "$CLIENT" models
```

Generate and download an image:

```bash
python "$CLIENT" generate \
  --model "Nano Banana2" \
  --prompt "A premium product photograph, precise studio lighting, clean composition" \
  --size "16:9" \
  --quality high \
  --output-dir "/absolute/path/to/output"
```

Edit one or more images:

```bash
python "$CLIENT" edit \
  --model "Nano Banana Pro" \
  --prompt "Keep the subject identity and pose; replace the background with a bright editorial studio" \
  --image "/absolute/path/reference-1.png" \
  --image "/absolute/path/reference-2.jpg" \
  --size "3:2" \
  --output-dir "/absolute/path/to/output"
```

Submit an asynchronous generation and wait for its result:

```bash
python "$CLIENT" generate \
  --async \
  --wait \
  --model "Nano Banana2" \
  --prompt "A cinematic city street after rain, detailed reflections, natural color" \
  --size "16:9" \
  --output-dir "/absolute/path/to/output"
```

Resume an existing job:

```bash
python "$CLIENT" wait "JOB_ID" --output-dir "/absolute/path/to/output"
```

## Handle Results

- Read the JSON printed to stdout. Generated local paths appear in `saved_files`; polling progress appears only on stderr.
- The CLI omits large `b64_json` strings from terminal output after saving them. Add the global `--include-base64` option before the subcommand only when the raw inline payload is required.
- Prefer `response_format=url` and download immediately. Relay URLs expire after about 6 hours.
- Use `--response-format b64_json` when a downstream client requires inline image data.
- Pass exact model IDs, including spaces or Chinese characters, inside quotes.
- Use one image per request unless the user explicitly asks for variants or batching.
- Do not silently switch models after moderation, balance, or capacity errors. Report the error and ask before changing cost or model behavior.
- The documented asynchronous image endpoint covers text-to-image generation. Keep image edits synchronous unless the relay documentation adds an async edit endpoint.
- Show completed images with absolute local Markdown paths when working in the Codex app.

Read [references/api.md](references/api.md) when selecting parameters, validating sizes, interpreting job responses, or troubleshooting API errors.
