# Draw Relay API Reference

## Endpoints

- OpenAI-compatible base: `https://draw.hugusir.top/api/v1`
- List models: `GET /models`
- Text-to-image: `POST /images/generations`
- Image-to-image: `POST /images/edits`
- Async generation base: `https://draw.hugusir.top/api/ai-jobs`
- Submit async text-to-image: `POST /images/generations`
- Read async job: `GET /{JOB_ID}`

Authenticate with `Authorization: Bearer YOUR_API_KEY`. The service also documents `X-Api-Key` and `X-Access-Key`, but the bundled client uses Bearer authentication.

## Models

Always treat `GET /models` as authoritative. Models observed during skill creation included:

- `Nano Banana2`
- `Nano Banana Pro`
- `gemini-2.5-flash-image`
- `gpt-image-2`
- `gpt-image-2-4K 高质量线路`

`Nano Banana2`, `Nano Banana Pro`, and the high-quality 4K route support commercial-grade native 4K output according to the relay documentation. `gemini-2.5-flash-image` is a fast 1K route.

## Text-To-Image JSON

Required fields:

- `model`: exact model ID.
- `prompt`: describe subject, scene, composition, style, lighting, materials, color, text constraints, and exclusions as needed.

Optional fields:

- `n`: number of images, default `1`.
- `size`: aspect ratio such as `1:1`, `3:2`, or `16:9`, or a pixel size. Unsupported pixels are normalized to the nearest allowed ratio and model tier.
- `quality`: commonly `high`, `medium`, `low`, or `standard`.
- `style`: commonly `natural` or `vivid`.
- `background`: commonly `opaque`, `transparent`, or `auto`; transparency depends on model support.
- `response_format`: `url` or `b64_json`, default `url`.
- `output_format`: commonly `png`, `jpeg`, or `webp` when supported.
- `upscale`: output tier such as `1k`, `2k`, or `4k` when supported. Invalid or missing values normalize to 1K.

## Image-To-Image Multipart

Send `multipart/form-data` to `/images/edits`.

- Send one reference as `image`.
- Send multiple references as repeated `image[]` fields. Repeated `image` fields are also compatible.
- Send an optional mask as `mask`; whether it takes effect depends on the model.
- Include `model` and `prompt` as form fields.
- Include the same optional controls used by text-to-image as form fields.
- Limit requests to 8 reference images and 40 MB total reference data.

## Async Jobs

Submit the same JSON body used by text-to-image to `/api/ai-jobs/images/generations`. The create response contains a job identifier. Poll `/api/ai-jobs/{JOB_ID}` until the status reaches a terminal state.

The bundled client recognizes these success states: `success`, `succeeded`, `completed`, `complete`, `done`.

It recognizes these failure states: `failed`, `failure`, `error`, `cancelled`, `canceled`.

On success, `responseBody` contains the original image API response. On failure, `errorMessage` contains a readable error. The client also tolerates common snake_case and nested wrapper variants.

## Size Matrix

| Ratio | 1K | 2K | 4K |
|---|---:|---:|---:|
| `1:1` | 1024 x 1024 | 2048 x 2048 | 2880 x 2880 |
| `3:2` | 1536 x 1024 | 2160 x 1440 | 3456 x 2304 |
| `2:3` | 1024 x 1536 | 1440 x 2160 | 2304 x 3456 |
| `16:9` | 1280 x 720 | 2560 x 1440 | 3840 x 2160 |
| `9:16` | 720 x 1280 | 1440 x 2560 | 2160 x 3840 |
| `4:3` | 1024 x 768 | 2048 x 1536 | 3200 x 2400 |
| `3:4` | 768 x 1024 | 1536 x 2048 | 2400 x 3200 |
| `21:9` | 1920 x 816 | 3120 x 1344 | 3840 x 1648 |

## Response And Storage

OpenAI-compatible image responses contain `data[]` entries with either `url` or `b64_json`. URL responses may also include `storageKey`, `mimeType`, and `bytes`.

The relay may return `b64_json` for image edits even when `response_format=url` was requested. The bundled client handles either form and suppresses the large Base64 string from terminal output by default.

Generated URLs are temporary and documented to expire after 6 hours with HTTP 410. Download or transfer them promptly. The relay states that API result URLs point to original generated files without platform recompression.

## Common Errors

- `余额不足`: replenish account credit before retrying.
- `缺少模型名称`: include `model` in JSON or multipart fields.
- `请求内容过大`: reduce references to 8 or fewer and below 40 MB total.
- Size or ratio error: use the size matrix or a supported ratio.
- Channel congestion: wait and submit a new request; do not automatically retry a POST because it can duplicate a charged generation.
- HTTP 410 while downloading: the temporary image expired and must be regenerated.
