# API Endpoints and Commands Reference

**Audience:** All — integration developers, engineers, ops  
**Last updated:** 2026-05-15

---

## Port summary

| Port | Protocol | Purpose |
|---|---|---|
| `20100/TCP` | Plain text over TCP | Service switcher — activate a service |
| `30100/TCP` | JSON over TCP | Service switcher — read status |
| `30000/TCP` | HTTP/1.1 | AI service — inference, health, and schema |

Node address: `192.168.8.5`

---

## Section 1 — Switcher command port (TCP 20100)

### Send a switch command

Connect to `192.168.8.5:20100`, send a UTF-8 line, read the reply.

**Request format**

```
start <service-name>\n
```

The trailing newline (`\n`) is **required**. Without it the connection hangs until the 5-second read deadline fires.

**Reply values**

| Reply | Meaning |
|---|---|
| `ok` | Switch accepted; `systemctl start` completed |
| `busy` | A switch is already running; the request is queued (one slot) |
| `error` | Unknown service name, invalid command format, or systemctl failure |

**Example — using netcat**

```bash
echo "start image-sdxl" | nc 192.168.8.5 20100
```

**Example — using Python**

```python
import socket

def switch_service(host: str, port: int, service: str, timeout: float = 10.0) -> str:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(f"start {service}\n".encode())
        return s.recv(256).decode().strip()

reply = switch_service("192.168.8.5", 20100, "image-sdxl")
print(reply)  # "ok"
```

**All valid service names**

```
image-flux          image-qwen          image-sdxl          image-sdxl-turbo
tts-coqui           tts-f5              tts-qwen3-clone     tts-qwen3-design     tts-qwen3-studio
video-animatediff   video-ltx           video-svd
llm-gpt120b         llm-gpt20b          llm-llama70b        llm-mixtral-llama70b
llm-mixtral8x22b    llm-nemotron-nano   llm-nemotron-super  llm-qwen327b         llm-wizardlm8x22b
translator-accurate translator-fast     translator-medium
```

---

## Section 2 — Switcher status port (TCP 30100)

Connect, read the response, close. No request body needed.

**Example**

```bash
nc 192.168.8.5 30100
```

**Response schema**

```json
{
  "healthy": true,
  "last_activated": "image-sdxl",
  "active_task": false,
  "task_started_at": "2026-05-15T19:36:00Z",
  "task_done_at": "2026-05-15T19:36:05Z",
  "pending_switch": ""
}
```

| Field | Type | Description |
|---|---|---|
| `healthy` | bool | Always `true` when the switcher is running |
| `last_activated` | string | Name of the most recently started service |
| `active_task` | bool | `true` while a `systemctl start` is in progress |
| `task_started_at` | string (RFC3339) | When the current or last switch began |
| `task_done_at` | string (RFC3339) | When the last switch completed |
| `pending_switch` | string | Name of the queued next switch, or `""` |

**Python example**

```python
import socket, json

def get_status(host: str, port: int, timeout: float = 10.0) -> dict:
    with socket.create_connection((host, port), timeout=timeout) as s:
        return json.loads(s.recv(4096).decode())

status = get_status("192.168.8.5", 30100)
print(status["last_activated"])
```

---

## Section 3 — Service health endpoint (HTTP GET /health)

All 24 services expose the same health path on port 30000.

```
GET http://192.168.8.5:30000/health
```

No body, no authentication, no headers required.

**Success response**

```
HTTP 200
{"status": "ok"}
```

**Not-ready responses**

| Condition | Behavior |
|---|---|
| Service not yet started | `Connection refused` |
| Service starting up | `Connection refused` or HTTP 5xx |
| Wrong service active | HTTP 4xx / 5xx or unexpected body |

**Readiness poll pattern**

```python
import time, urllib.request, urllib.error

def wait_ready(url: str, timeout: float = 900, interval: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(interval)
    return False

ready = wait_ready("http://192.168.8.5:30000/health")
```

---

## Section 4 — OpenAPI schema endpoint

Every running service exposes its own OpenAPI 3.0 schema.

```
GET http://192.168.8.5:30000/openapi.json
```

Useful to discover exact field names and types for the currently active service.

```bash
curl -s http://192.168.8.5:30000/openapi.json | python3 -m json.tool | less
```

---

## Section 5 — Image generation (POST /generate)

**Services:** `image-flux`, `image-qwen`, `image-sdxl`, `image-sdxl-turbo`  
**GPU lane:** NVIDIA

```
POST http://192.168.8.5:30000/generate
Content-Type: application/json
```

### Request schema (`GenerateRequest`)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | yes | — | Text description of the image |
| `negative_prompt` | string | no | — | What to exclude from the image |
| `width` | integer | no | service default | Pixel width |
| `height` | integer | no | service default | Pixel height |
| `steps` | integer | no | service default | Diffusion steps |
| `guidance_scale` | float | no | service default | CFG scale |
| `seed` | integer | no | random | Fixed seed for reproducibility |

### Response

```
HTTP 200
Content-Type: image/png
Body: raw PNG bytes
```

### Examples

**Minimal request (all defaults)**

```bash
curl -s -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a red apple on a wooden table"}' \
  --output apple.png
```

**SDXL full-quality request**

```bash
curl -s -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A serene Japanese garden, cherry blossoms, koi pond, soft morning mist",
    "negative_prompt": "blurry, low quality, watermark, distorted",
    "width": 1024,
    "height": 1024,
    "steps": 25
  }' \
  --output garden.png
```

**SDXL-Turbo fast request (4 steps max)**

```bash
curl -s -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "cyberpunk city at night", "width": 512, "height": 512, "steps": 4}' \
  --output city.png
```

**Readiness probe (fast, low cost)**

```bash
curl -sf -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "width": 64, "height": 64, "steps": 1}' \
  --output /dev/null
```

### Per-service notes

| Service | Native resolution | Recommended steps | Notes |
|---|---|---|---|
| `image-flux` | 512×512 | 20 | — |
| `image-qwen` | varies | — | Schema may differ; probe `/openapi.json` |
| `image-sdxl` | 1024×1024 | 20–30 | Best quality at native resolution |
| `image-sdxl-turbo` | 512×512 | **1–4 max** | Do not exceed 4 steps |

---

## Section 6 — Text-to-speech (POST /tts)

**Services:** `tts-coqui`, `tts-f5`, `tts-qwen3-clone`, `tts-qwen3-design`, `tts-qwen3-studio`  
**GPU lane:** NVIDIA

```
POST http://192.168.8.5:30000/tts
Content-Type: application/json
```

### Request schema (`RouterTTSRequest`)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `text` | string | yes | — | Text to synthesize |
| `language` | string | no | — | Language code, e.g. `"en"` |
| `speaker_wav` | string | no | — | Reference speaker WAV path (for cloning) |
| `pace` | string | no | `"normal"` | Speaking pace |

### Response

```
HTTP 200
Content-Type: audio/wav  (or audio/mpeg)
Body: raw WAV or MP3 bytes
```

### Voice listing

```bash
GET http://192.168.8.5:30000/voices
```

Returns a list of available speaker names. **Must be non-empty** for synthesis to succeed. If empty, `/tts` returns `404 {"detail": "Voice '<name>' not found"}`.

### Examples

**Basic synthesis**

```bash
curl -s -X POST http://192.168.8.5:30000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test.", "language": "en"}' \
  --output output.wav
```

**Check available voices**

```bash
curl -s http://192.168.8.5:30000/voices
```

### Deployment prerequisite

Voice reference audio files must be installed in the service's voice directory on the node before any TTS service can generate audio. The exact directory depends on the service unit configuration (not verified from repository code — **Not verified**).

---

## Section 7 — Video generation (POST /generate)

**Services:** `video-animatediff`, `video-ltx`, `video-svd`  
**GPU lane:** NVIDIA  
**Endpoint:** Same path as image services

```
POST http://192.168.8.5:30000/generate
Content-Type: application/json
```

### Request schema

Same `GenerateRequest` as image services, with additional video fields:

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | yes | — | — |
| `width` | integer | no | service default | — |
| `height` | integer | no | service default | — |
| `frames` | integer | no | service default | Frame count |
| `fps` | integer | no | service default | Output frames per second |
| `steps` | integer | no | service default | — |

### Response

```
HTTP 200
Content-Type: video/mp4  (or image/gif, or application/json with base64)
Body: binary video bytes, or JSON {"video": "<base64>"}
```

When the response is JSON, the base64 value in common fields (`video`, `data`, `result`, `output`) contains the binary video; strip any `data:<mime>;base64,` prefix before decoding.

### Examples

**AnimateDiff (GIF/MP4)**

```bash
curl -s -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "ocean beach at sunset, gentle waves",
    "width": 512, "height": 512,
    "frames": 16, "fps": 8, "steps": 20
  }' \
  --output beach.mp4
```

**LTX-Video (16:9)**

```bash
curl -s -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "timelapse of clouds over mountains",
    "width": 512, "height": 288,
    "frames": 25, "fps": 8, "steps": 30
  }' \
  --output clouds.mp4
```

### Per-service notes

| Service | Native resolution | Frames | Notes |
|---|---|---|---|
| `video-animatediff` | 512×512 | 16 | Response may be MP4 or GIF |
| `video-ltx` | 512×288 | 25 | 16:9 native ratio |
| `video-svd` | 1024×576 | 25 | Stable Video Diffusion, cinematic quality |

---

## Section 8 — Large language models (POST /v1/chat/completions)

**Services:** `llm-gpt120b`, `llm-gpt20b`, `llm-llama70b`, `llm-mixtral-llama70b`, `llm-mixtral8x22b`, `llm-nemotron-nano`, `llm-nemotron-super`, `llm-qwen327b`, `llm-wizardlm8x22b`  
**GPU lane:** AMD (ROCm)  
**Backend:** llama-server (OpenAI-compatible API)

```
POST http://192.168.8.5:30000/v1/chat/completions
Content-Type: application/json
```

### Request schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `messages` | array | yes | Array of `{"role": "user"|"assistant"|"system", "content": "..."}` |
| `max_tokens` | integer | no | Maximum tokens to generate |
| `temperature` | float | no | Sampling temperature (0.0 = deterministic) |
| `stream` | bool | no | Not verified — check `/openapi.json` for streaming support |

### Response schema

```json
{
  "choices": [
    {
      "message": {"role": "assistant", "content": "<generated text>"},
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 87,
    "total_tokens": 99
  }
}
```

Extract generated text from `choices[0].message.content` (fallback: `choices[0].text`).

### Examples

**Basic chat request**

```bash
curl -s -X POST http://192.168.8.5:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain what a transformer is in one paragraph."}],
    "max_tokens": 200,
    "temperature": 0.7
  }'
```

**Deterministic code generation**

```bash
curl -s -X POST http://192.168.8.5:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Write a Python binary search function with type hints."}],
    "max_tokens": 400,
    "temperature": 0.2
  }'
```

**Readiness probe (minimal tokens)**

```bash
curl -sf -X POST http://192.168.8.5:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "hi"}], "max_tokens": 5, "temperature": 0.0}'
```

### Per-service notes

| Service | Parameters | GPU | Specialization |
|---|---|---|---|
| `llm-gpt120b` | 120B | AMD | Large, slow, high quality |
| `llm-gpt20b` | 20B | AMD | Medium size, creative tasks |
| `llm-llama70b` | 70B | AMD | General purpose |
| `llm-mixtral-llama70b` | 70B hybrid | AMD | Mixtral+LLaMA hybrid |
| `llm-mixtral8x22b` | 8×22B MoE | AMD | Code generation, low temperature |
| `llm-nemotron-nano` | small | AMD | Fast, lighter tasks |
| `llm-nemotron-super` | large | AMD | Deep analysis |
| `llm-qwen327b` | 27B | AMD | Qwen3 architecture |
| `llm-wizardlm8x22b` | 8×22B MoE | AMD | System design, long reasoning |

---

## Section 9 — Translation (POST /v1/translate)

**Services:** `translator-accurate`, `translator-fast`, `translator-medium`  
**GPU lane:** AMD (ROCm)

```
POST http://192.168.8.5:30000/v1/translate
Content-Type: application/json
```

### Request schema (`TranslateRequest`)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `text` | string | yes | — | Source text to translate |
| `src_lang` | string | yes | — | Source language code, e.g. `"en"` |
| `tgt_lang` | string | yes | — | Target language code, e.g. `"fr"` |
| `model` | string | no | service name | Override model name |
| `style_notes` | string | no | `""` | Free-text style instructions |

### Response schema

```json
{
  "translated_text": "<translation>",
  "src_lang": "en",
  "tgt_lang": "fr",
  "chunks": 2,
  "model": "translator-accurate"
}
```

### Examples

**Translate to French**

```bash
curl -s -X POST http://192.168.8.5:30000/v1/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Good morning, how are you?", "src_lang": "en", "tgt_lang": "fr"}'
```

**Translate to Spanish**

```bash
curl -s -X POST http://192.168.8.5:30000/v1/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "The weather is beautiful today.", "src_lang": "en", "tgt_lang": "es"}'
```

**Readiness probe**

```bash
curl -sf -X POST http://192.168.8.5:30000/v1/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "hello", "src_lang": "en", "tgt_lang": "fr"}'
```

### Per-service notes

| Service | Speed | Quality | Default target |
|---|---|---|---|
| `translator-accurate` | Slower | Highest | French (`fr`) |
| `translator-fast` | Fastest | Good | Spanish (`es`) |
| `translator-medium` | Medium | Medium | German (`de`) |

---

## Section 10 — Complete workflow example (Python)

```python
import socket, time, json
from urllib import request as urllib_request

HOST = "192.168.8.5"
CMD_PORT = 20100
STATUS_PORT = 30100
SVC_PORT = 30000

def switch(service: str) -> str:
    with socket.create_connection((HOST, CMD_PORT), timeout=10) as s:
        s.sendall(f"start {service}\n".encode())
        return s.recv(256).decode().strip()

def wait_ready(timeout: float = 300) -> bool:
    url = f"http://{HOST}:{SVC_PORT}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib_request.urlopen(url, timeout=10) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False

# 1. Activate LLM service
reply = switch("llm-nemotron-nano")
assert reply == "ok", f"Switch failed: {reply}"

# 2. Wait for it to be ready
assert wait_ready(), "Service did not become ready in time"

# 3. Send an inference request
req_body = json.dumps({
    "messages": [{"role": "user", "content": "Write a haiku about the ocean."}],
    "max_tokens": 50,
    "temperature": 0.7
}).encode()

req = urllib_request.Request(
    f"http://{HOST}:{SVC_PORT}/v1/chat/completions",
    data=req_body,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib_request.urlopen(req, timeout=60) as r:
    result = json.loads(r.read())

print(result["choices"][0]["message"]["content"])
```

---

## Evidence

- [main.go](../../main.go) — port definitions, command parsing
- [services.json](../../services.json) — valid service names
- [test/lan_workload_test_config.json](../../test/lan_workload_test_config.json) — all endpoint URLs and payloads
- [test/LAN_WORKLOAD_TEST.md](../../test/LAN_WORKLOAD_TEST.md) — endpoint schemas (Sections 6–8)
