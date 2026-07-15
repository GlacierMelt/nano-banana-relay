# Nano Banana Relay for Codex

A Codex skill for generating and editing images through the OpenAI-compatible relay at `https://draw.hugusir.top/api/v1`.

It supports:

- Text-to-image generation
- Single-image and multi-reference image editing
- Asynchronous generation, status polling, and result download
- Runtime model discovery
- URL and Base64 image responses
- `Nano Banana2`, `Nano Banana Pro`, `gemini-2.5-flash-image`, and other models exposed by the relay

## Install In Codex

Ask Codex:

```text
Use $skill-installer to install https://github.com/GlacierMelt/nano-banana-relay/tree/main/skills/nano-banana-relay
```

The skill becomes available on the next turn as `$nano-banana-relay`.

Alternatively, run the bundled installer directly:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo GlacierMelt/nano-banana-relay \
  --path skills/nano-banana-relay
```

## Configure

Create the highest-priority local auth file:

```json
{
  "_instructions": "Keep this file in ~/.codex, mode 600, and never commit it.",
  "OPENAI_API_KEY": "YOUR_API_KEY",
  "OPENAI_BASE_URL": "https://draw.hugusir.top/api/v1"
}
```

Save it as `~/.codex/nano-banana-relay-auth.json`, then restrict its permissions:

```bash
chmod 600 ~/.codex/nano-banana-relay-auth.json
```

Non-empty auth-file values override command-line arguments and environment variables. When the file is absent or a field is empty, these environment variables remain available as fallbacks:

```bash
export NANO_BANANA_API_KEY="YOUR_API_KEY"
export NANO_BANANA_BASE_URL="https://draw.hugusir.top/api/v1"
export NANO_BANANA_MODEL="Nano Banana2"
```

Select a different auth file with `NANO_BANANA_AUTH_FILE` or the global `--auth-file` CLI option.

## Use In Codex

Text-to-image:

```text
$nano-banana-relay 用 Nano Banana Pro 画：未来城市夜景，电影感，16:9
```

Image editing after attaching a reference image:

```text
$nano-banana-relay 用 Nano Banana2 改这张图：保留主体，把背景换成白色摄影棚
```

Asynchronous generation:

```text
$nano-banana-relay 用 Nano Banana Pro 异步画并等待：高端护肤品商业海报
```

Structured shorthand is also accepted:

```text
$nano-banana-relay model="Nano Banana Pro" size=16:9 prompt="未来城市夜景"
```

## Notes

- Model IDs must match the relay exactly. The skill can query the current model list before generation.
- The documented asynchronous endpoint covers text-to-image. Image editing is synchronous.
- Generated URLs are temporary and should be downloaded promptly.
- Generation requests may consume paid relay credits.
- This repository contains no API key. Never commit `nano-banana-relay-auth.json`.

## License

MIT
