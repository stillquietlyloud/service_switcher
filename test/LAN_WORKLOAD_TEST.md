# LAN Workload Test — Reference Documentation

**Files:** `test/lan_workload_test.py` · `test/lan_workload_test_config.json`  
**Last updated:** 2026-05-15  
**Audience:** engineers running or extending the test harness

---

## 1. Purpose

`lan_workload_test.py` is an end-to-end quality and performance test harness for every AI service managed by `service_switcher`. For each service it:

1. Sends a **switch command** to the switcher — telling it to start the target service.
2. Polls **`GET /health`** with a two-phase down→up strategy to detect when the old service has stopped and the new one is ready.
3. Sends a **real workload request** with a meaningful prompt or text and saves the produced artifact (PNG, WAV, MP3, MP4, plain text) alongside the script.
4. Runs **latency sampling** — 3 additional lightweight requests — to measure p50/p95/p99.
5. Writes a timestamped **JSON report** and a human-readable **text report**.

The test can be run from any host with network access to the switcher and service endpoints. It requires no dependencies beyond the Python 3 standard library.

---

## 2. Quick Start

```bash
# Run all services (group order: nvidia first, then amd)
python3 test/lan_workload_test.py

# Run only NVIDIA services
python3 test/lan_workload_test.py --groups nvidia

# Run only AMD services (LLM + translator)
python3 test/lan_workload_test.py --groups amd

# Run specific services by name
python3 test/lan_workload_test.py --services image-sdxl translator-accurate

# Use a custom config path
python3 test/lan_workload_test.py --config /path/to/config.json
```

### Important: service-stopper requirement

Certain cross-lane transitions — specifically `llm` ↔ `tts/image/video` — require `service-stopper.service` to be active on the AI node. The script checks and warns if it is not:

```
WARNING: service-stopper.service is NOT active on this host.
         LLM<->NVIDIA service transitions (llm<->tts/image/video) require ...
         Start it with: sudo systemctl start service-stopper.service
```

Translator services have `Conflicts=` entries covering all other services and do **not** need service-stopper.

---

## 3. Network Topology

| Purpose | Host | Port | Protocol |
|---------|------|------|----------|
| Switcher command | 192.168.8.5 | 20100 | TCP (plain text) |
| Switcher status | 192.168.8.5 | 30100 | TCP (JSON response) |
| Service workload + health | 192.168.8.5 | 30000 | HTTP/1.1 |

All service types share port 30000. Only one service is active on that port at a time, managed by systemd `Conflicts=` and the switcher.

---

## 4. Configuration Schema

`lan_workload_test_config.json` is the single source of truth for addresses, timeouts, and per-service payloads.

### Top-level fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `switcher_host` | string | — | IP/hostname of the AI node running the switcher |
| `command_port` | int | 20100 | TCP port for switch commands |
| `status_port` | int | 30100 | TCP port for switcher status JSON |
| `health_base_url` | string | — | Base URL for the service health endpoint; `/health` is appended |
| `group_order` | string[] | `["nvidia","amd"]` | Processing order when no `--groups` filter is given |
| `timeouts.socket_seconds` | float | 10 | TCP connect/read timeout for switcher ports |
| `timeouts.http_seconds` | float | 300 | HTTP timeout for individual workload requests |
| `timeouts.readiness_seconds` | float | 900 | Maximum time to wait for a service to become ready |
| `poll_interval_seconds` | float | 3.0 | Interval between readiness poll attempts (Phase 2) |
| `latency_requests` | int | 3 | Number of additional probe requests after the workload for latency stats |
| `service_tests` | object[] | — | List of per-service test definitions (see below) |

### Per-service test object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service_name` | string | yes | Exact name passed to the switcher (`start <name>`) |
| `group` | string | yes | `"nvidia"` or `"amd"` — controls execution order |
| `service_type` | string | yes | `"image"`, `"tts"`, `"video"`, `"llm"`, or `"translator"` — controls artifact extraction |
| `endpoint_url` | string | yes | Full URL for the workload POST request |
| `method` | string | yes | HTTP method, always `"POST"` for workloads |
| `readiness_payload` | object | yes | Lightweight JSON body used during latency sampling |
| `workload_payload` | object | yes | Full JSON body sent for the quality workload request |
| `expected_status_codes` | int[] | yes | HTTP status codes that count as success (always `[200]`) |
| `quality_criteria` | string | yes | Human-readable quality evaluation rubric written to the report |
| `notes` | string | no | Deployment notes and known issues |

---

## 5. Per-Service Test Cycle

Each service goes through exactly seven sequential steps inside `run_service_test()`:

```
Step 1  →  Switch command (TCP → switcher:20100)
Step 2  →  Status snapshot (TCP → switcher:30100)
Step 3  →  Readiness poll — two-phase GET /health
Step 4  →  Workload request (HTTP POST → service:30000/<path>)
Step 5  →  Artifact extraction and save
Step 6  →  Latency sampling (3 × lightweight POST)
Step 7  →  Pass / fail determination
```

### Step 1 — Switch command

```
TCP connect  →  192.168.8.5:20100
Send:            "start <service_name>\n"
Read up to:      256 bytes
Expected reply:  "ok"
```

If the reply is anything other than `"ok"` the test is aborted immediately and the result is marked `failed`.

### Step 2 — Status snapshot

```
TCP connect  →  192.168.8.5:30100
Read up to:      4096 bytes
Parse as JSON.
```

The response (containing `last_activated`, `healthy`, etc.) is saved verbatim in the JSON report under `status_snapshot`. It is not used for pass/fail logic.

### Step 3 — Readiness polling (`GET /health`)

Health checks are always `GET http://192.168.8.5:30000/health` with no body. The poll runs in two phases:

**Phase 1 — wait for old service to go DOWN**

```
Poll every 1s for up to 15s.
On each attempt:  GET /health  (no body, HTTP timeout = timeouts.http_seconds)
Exit Phase 1 when:
  - transport fails (Connection refused), OR
  - HTTP status is not in expected_status_codes (e.g. 503)
If health stays up for the full 15s, assume this is already the correct
service (same-lane switch that didn't require a stop), skip to Phase 2.
```

**Phase 2 — wait for new service to come UP**

```
Poll every poll_interval_seconds (3s) for up to readiness_seconds (900s).
On each attempt:  GET /health  (no body)
Exit Phase 2 when:
  - HTTP 200 received  →  ready=True
  - timeout exceeded   →  ready=False, test aborted
```

Total warm-up time (Phase 1 + Phase 2) is recorded as `warmup_seconds` in the report.

### Step 4 — Workload request

```
POST <endpoint_url>
Content-Type: application/json
Accept: */*
Body: JSON-serialized workload_payload
HTTP timeout: timeouts.http_seconds (300s)
Max response size: 64 MB
```

Exact endpoint URLs and payloads are detailed per service type in Section 6.

### Step 5 — Artifact extraction and save

Artifact handling depends on `service_type`:

| service_type | Extraction logic |
|---|---|
| `llm` | Parse JSON, extract `choices[0].message.content` (or `choices[0].text`). Save as `.txt`. |
| `translator` | Parse JSON, extract `translated_text`. Save as `.txt`. |
| `image` | Response body is raw PNG/JPEG bytes. Detect format from magic bytes. Save as `.png` / `.jpg`. |
| `tts` | Response body is raw WAV/MP3 bytes. Detect from magic bytes. Save as `.wav` / `.mp3`. |
| `video` | Response body is raw MP4 or binary. Detect from magic bytes; fall back to base64 scan in JSON. |

If the response is `application/json` for non-LLM/translator types, the extractor scans common field names (`image`, `audio`, `video`, `data`, `result`, `output`, `content`, `file`) for base64-encoded binary and decodes + identifies it by magic bytes.

Artifact filename format: `workload_<YYYYMMDD_HHMMSSz>_<service-name>.<ext>`  
Saved to: the directory containing `lan_workload_test.py` (`test/`)

### Step 6 — Latency sampling

After the workload, three additional HTTP POST requests are sent using `readiness_payload` (lightweight body). The workload response time is included as the first sample, giving 4 total samples. Computed statistics: `min`, `max`, `avg`, `p50`, `p95`, `p99` (nearest-rank percentile).

### Step 7 — Pass/fail

`passed` if and only if:
- Switch replied `"ok"`
- Service became ready within `readiness_seconds`
- Workload HTTP status is in `expected_status_codes` (HTTP 200)
- Transport succeeded (no connection errors)

---

## 6. Exact Endpoint Calls by Service Type

### 6.1 Image services (`service_type: "image"`)

All image services expose a FastAPI app on NVIDIA GPUs. The workload and readiness probe both use the same endpoint.

```
POST http://192.168.8.5:30000/generate
Content-Type: application/json

Readiness probe body (lightweight):
  {"prompt": "test", "width": 64, "height": 64, "steps": 1}

Response: raw PNG bytes (Content-Type: image/png)
```

**Full request schema** (`GenerateRequest`):
| Field | Type | Required | Default |
|---|---|---|---|
| `prompt` | string | yes | — |
| `negative_prompt` | string | no | — |
| `width` | integer | no | 0 (service default) |
| `height` | integer | no | 0 (service default) |
| `steps` | integer | no | 0 (service default) |
| `guidance_scale` | float | no | 0.0 (service default) |
| `seed` | integer | no | — (random) |

**Per-service workload payloads:**

| Service | Prompt summary | width | height | steps |
|---------|---------------|-------|--------|-------|
| `image-flux` | Snow-capped mountain at golden hour | 512 | 512 | 20 |
| `image-qwen` | Cozy cabin in snowy forest at night | — | — | — |
| `image-sdxl` | Japanese garden, cherry blossoms, koi pond (Ghibli style) | 1024 | 1024 | 25 |
| `image-sdxl-turbo` | Cyberpunk city at night with neon reflections | 512 | 512 | 4 |

`image-sdxl` also sends `"negative_prompt": "blurry, low quality, watermark, distorted, ugly"`.

### 6.2 TTS services (`service_type: "tts"`)

All TTS services expose a FastAPI app on NVIDIA GPUs.

```
POST http://192.168.8.5:30000/tts
Content-Type: application/json

Readiness probe body (lightweight):
  {"text": "test"}

Response: raw audio bytes (WAV or MP3)
```

**Full request schema** (`RouterTTSRequest`):
| Field | Type | Required | Default |
|---|---|---|---|
| `text` | string | yes | — |
| `language` | string | no | — |
| `speaker_wav` | string | no | — |
| `pace` | string | no | `"normal"` |

> **Deployment requirement:** `GET http://192.168.8.5:30000/voices` must return a non-empty list. Until voice reference files are installed in the service's voice directory, all `/tts` calls return `404 {"detail": "Voice '<name>' not found"}`.

**Per-service workload payloads:**

| Service | Text (summarized) | language |
|---------|------------------|----------|
| `tts-coqui` | Clarity and prosody evaluation sentence | `"en"` |
| `tts-f5` | Pangrams covering full English phoneme range | `"en"` |
| `tts-qwen3-clone` | Voice cloning evaluation with varied punctuation | `"en"` |
| `tts-qwen3-design` | Professional assistant greeting and offer | `"en"` |
| `tts-qwen3-studio` | Broadcast-ready studio synthesis evaluation | `"en"` |

### 6.3 Video services (`service_type: "video"`)

Video services follow the same pattern as image services (same endpoint, same schema).

```
POST http://192.168.8.5:30000/generate
Content-Type: application/json

Readiness probe body (lightweight):
  {"prompt": "test", "frames": 4, "steps": 1}

Response: binary video (MP4, GIF) or JSON with base64-encoded video
```

**Per-service workload payloads:**

| Service | Prompt summary | width | height | frames | fps | steps |
|---------|---------------|-------|--------|--------|-----|-------|
| `video-animatediff` | Ocean beach at sunset, gentle waves | 512 | 512 | 16 | 8 | 20 |
| `video-ltx` | Cloud timelapse over mountains, golden hour to dusk | 512 | 288 | 25 | 8 | 30 |
| `video-svd` | Slow forest pan, cinematic depth of field | 1024 | 576 | 25 | 6 | 25 |

### 6.4 LLM services (`service_type: "llm"`)

LLM services run via `llama-server` on AMD ROCm GPUs, exposing an OpenAI-compatible chat completions API.

```
POST http://192.168.8.5:30000/v1/chat/completions
Content-Type: application/json

Readiness probe body (lightweight):
  {
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 5,
    "temperature": 0.0
  }

Response (JSON):
  {
    "choices": [
      {
        "message": {"role": "assistant", "content": "<generated text>"},
        "finish_reason": "stop"
      }
    ],
    "usage": {...}
  }
```

The generated text is extracted from `choices[0].message.content` (falls back to `choices[0].text`) and saved as a `.txt` artifact.

**Per-service workload payloads:**

| Service | Task | max_tokens | temperature |
|---------|------|-----------|-------------|
| `llm-gpt120b` | Explain transformer self-attention (Q/K/V matrices) | 250 | 0.7 |
| `llm-gpt20b` | Creative story: astronaut finds alien library on Mars | 250 | 0.85 |
| `llm-llama70b` | Distinguish supervised/unsupervised/reinforcement learning with examples | 350 | 0.7 |
| `llm-mixtral-llama70b` | 5 distributed systems HA design considerations | 350 | 0.7 |
| `llm-mixtral8x22b` | Python binary search with type hints and edge cases | 400 | 0.2 |
| `llm-nemotron-nano` | 5 practical Python clean-code tips | 250 | 0.7 |
| `llm-nemotron-super` | Monolith vs microservices for 50k orders/day e-commerce | 450 | 0.7 |
| `llm-qwen327b` | NumPy feedforward NN: forward pass, loss, backprop | 400 | 0.5 |
| `llm-wizardlm8x22b` | Design recommendation system for 10M users (4 components) | 450 | 0.7 |

### 6.5 Translator services (`service_type: "translator"`)

Translator services run via `uvicorn` on AMD ROCm GPUs (Aya Expanse / llama.cpp backend).

```
POST http://192.168.8.5:30000/v1/translate
Content-Type: application/json

Readiness probe body (lightweight):
  {"text": "hello", "src_lang": "en", "tgt_lang": "<target>"}

Response (JSON):
  {
    "translated_text": "<translation>",
    "src_lang": "en",
    "tgt_lang": "<target>",
    "chunks": <int>,
    "model": "<service-name>"
  }
```

**Full request schema** (`TranslateRequest`):
| Field | Type | Required | Default |
|---|---|---|---|
| `model` | string | no | service name |
| `text` | string | yes | — |
| `src_lang` | string | yes | — |
| `tgt_lang` | string | yes | — |
| `style_notes` | string | no | `""` |

The translated text is extracted from `translated_text` and saved as a `.txt` artifact.

**Per-service workload payloads:**

| Service | Source text (summarized) | src_lang | tgt_lang |
|---------|------------------------|----------|----------|
| `translator-accurate` | AI transforms how we live and work; ML models handle complex tasks | `en` | `fr` |
| `translator-fast` | Nice weather, going to the park for a picnic with family | `en` | `es` |
| `translator-medium` | Technology makes cross-language communication easier; global collaboration | `en` | `de` |

---

## 7. Health Endpoint

All services expose a health endpoint at the same path regardless of type:

```
GET http://192.168.8.5:30000/health
(no body, no headers required)

Success response:
  HTTP 200  {"status": "ok"}

Failure / not yet ready:
  Connection refused, HTTP 5xx, or no response
```

This endpoint is the only one used for readiness polling. Workload endpoints are never used as health probes.

---

## 8. Switcher Protocol

### Command port (20100)

```
TCP connect  →  192.168.8.5:20100  (timeout = socket_seconds = 10s)
Send (UTF-8): "start <service_name>\n"
Read (up to 256 bytes):
  "ok"      → switch accepted
  anything else → switch rejected, test aborted
```

### Status port (30100)

```
TCP connect  →  192.168.8.5:30100  (timeout = socket_seconds = 10s)
Read (up to 4096 bytes):
  JSON object with at minimum:
    last_activated: string   (name of last started service)
    healthy: bool
```

---

## 9. Report Format

### JSON report (`workload_report_<stamp>.json`)

```json
{
  "timestamp_utc": "2026-05-15T19:53:19.201800+00:00",
  "config_path": "/git/service_switcher/test/lan_workload_test_config.json",
  "command_address": "192.168.8.5:20100",
  "status_address": "192.168.8.5:30100",
  "active_groups": ["nvidia", "amd"],
  "selected_services": null,
  "summary": {
    "total": 1,
    "passed": 1,
    "failed": 0,
    "artifacts_saved": 1
  },
  "results": [
    {
      "service_name": "image-sdxl",
      "group": "nvidia",
      "endpoint_url": "http://192.168.8.5:30000/generate",
      "switch_ok": true,
      "switch_response": "ok",
      "switch_elapsed_seconds": 0.026,
      "status_snapshot": {...},
      "warmup_seconds": 9.0,
      "workload_ok": true,
      "workload_status_code": 200,
      "workload_content_type": "image/png",
      "workload_elapsed_seconds": 8.623,
      "workload_snippet": "<first 1000 chars of response or decoded text>",
      "artifact_path": "/git/service_switcher/test/workload_20260515_195653Z_image-sdxl.png",
      "artifact_size_bytes": 1458144,
      "artifact_content_type": "image/png",
      "latency_seconds": {
        "min": 0.022,
        "max": 8.623,
        "avg": 2.213,
        "p50": 0.048,
        "p95": 8.623,
        "p99": 8.623
      },
      "latency_sample_count": 4,
      "quality_criteria": "...",
      "notes": "...",
      "result": "passed",
      "message": "ok"
    }
  ]
}
```

### Text report (`workload_report_<stamp>.txt`)

Human-readable, one block per service. Includes service name, endpoint, switch result, warm-up time, workload result, artifact filename + size, latency stats, quality rubric, and result. For `llm` and `translator` services, the full generated text is included under `response:`.

---

## 10. Service Inventory

### NVIDIA group (image / TTS / video — port 30000)

| # | Service | Type | Endpoint | GPU lane |
|---|---------|------|----------|----------|
| 1 | `image-flux` | image | `POST /generate` | NVIDIA |
| 2 | `image-qwen` | image | `POST /generate` | NVIDIA |
| 3 | `image-sdxl` | image | `POST /generate` | NVIDIA |
| 4 | `image-sdxl-turbo` | image | `POST /generate` | NVIDIA |
| 5 | `tts-coqui` | tts | `POST /tts` | NVIDIA |
| 6 | `tts-f5` | tts | `POST /tts` | NVIDIA |
| 7 | `tts-qwen3-clone` | tts | `POST /tts` | NVIDIA |
| 8 | `tts-qwen3-design` | tts | `POST /tts` | NVIDIA |
| 9 | `tts-qwen3-studio` | tts | `POST /tts` | NVIDIA |
| 10 | `video-animatediff` | video | `POST /generate` | NVIDIA |
| 11 | `video-ltx` | video | `POST /generate` | NVIDIA |
| 12 | `video-svd` | video | `POST /generate` | NVIDIA |

### AMD group (LLM / translator — port 30000)

| # | Service | Type | Endpoint | GPU lane |
|---|---------|------|----------|----------|
| 13 | `llm-gpt120b` | llm | `POST /v1/chat/completions` | AMD |
| 14 | `llm-gpt20b` | llm | `POST /v1/chat/completions` | AMD |
| 15 | `llm-llama70b` | llm | `POST /v1/chat/completions` | AMD |
| 16 | `llm-mixtral-llama70b` | llm | `POST /v1/chat/completions` | AMD |
| 17 | `llm-mixtral8x22b` | llm | `POST /v1/chat/completions` | AMD |
| 18 | `llm-nemotron-nano` | llm | `POST /v1/chat/completions` | AMD |
| 19 | `llm-nemotron-super` | llm | `POST /v1/chat/completions` | AMD |
| 20 | `llm-qwen327b` | llm | `POST /v1/chat/completions` | AMD |
| 21 | `llm-wizardlm8x22b` | llm | `POST /v1/chat/completions` | AMD |
| 22 | `translator-accurate` | translator | `POST /v1/translate` | AMD |
| 23 | `translator-fast` | translator | `POST /v1/translate` | AMD |
| 24 | `translator-medium` | translator | `POST /v1/translate` | AMD |

---

## 11. systemd Conflicts= and Switching Rules

Understanding which services conflict is critical for test ordering and knowing when `service-stopper` is required.

| When switching to... | Stops automatically (via Conflicts=) | Needs service-stopper? |
|---|---|---|
| Any NVIDIA image service | Other NVIDIA image/TTS/video services | No — same lane |
| Any NVIDIA TTS service | Other NVIDIA image/TTS/video services | No — same lane |
| `translator-accurate/fast/medium` | **ALL** services (cross-lane full coverage) | No |
| Any LLM service | Other LLM services + all translator services | **Yes** for NVIDIA→LLM |

`translator-accurate.service Conflicts=` covers: image-flux, image-qwen, image-sdxl, image-sdxl-turbo, tts-coqui, tts-f5, tts-qwen3-*, video-animatediff, video-ltx, video-svd, llm.service, llm-ultimate, llm-gpt120b, llm-gpt20b, llm-nemotron-super, llm-wizardlm8x22b, llm-llama70b, translator-fast, translator-medium.

**Recommended test sequences without service-stopper:**

```bash
# Run NVIDIA services (they all share one Conflicts= lane)
python3 test/lan_workload_test.py --groups nvidia

# Use translator as a bridge to stop the last NVIDIA service
echo 'start translator-accurate' | nc -w3 192.168.8.5 20100
sleep 30  # wait for translator to be ready

# Now run AMD group (translator is running; starting LLM stops translator via Conflicts=)
python3 test/lan_workload_test.py --groups amd
```

---

## 12. Known Deployment Issues

| Issue | Affected services | Symptom | Fix |
|---|---|---|---|
| No voice files installed | `tts-f5`, `tts-coqui`, `tts-qwen3-*` | `404 {"detail": "Voice 'en-female' not found"}` | Install speaker reference audio; `GET /voices` must return non-empty list |
| service-stopper not running | LLM tests after NVIDIA group | NVIDIA service keeps port 30000; LLM fails to bind | `sudo systemctl start service-stopper.service` |
| Video service unit files may not exist | `video-animatediff`, `video-ltx`, `video-svd` | Switcher returns error; test marks as failed | Deploy video service unit files |

---

## 13. Artifact Detection Logic

When the raw response bytes do not have an unambiguous `Content-Type`, the script identifies the format by **magic byte signatures**:

| Signature | Detected type |
|---|---|
| `\x89PNG\r\n\x1a\n` (8 bytes) | `image/png` |
| `\xff\xd8\xff` (3 bytes) | `image/jpeg` |
| `RIFF....WEBP` | `image/webp` |
| `GIF87a` / `GIF89a` | `image/gif` |
| `....ftyp` at offset 4 | `video/mp4` |
| `ID3` or MPEG sync `0xFF 0xEx` | `audio/mpeg` |
| `RIFF....WAVE` | `audio/wav` |
| `OggS` | `audio/ogg` |
| `fLaC` | `audio/flac` |

For JSON responses from non-LLM/translator types, the extractor scans these field names for base64-encoded binary: `image`, `audio`, `video`, `data`, `result`, `output`, `content`, `file`. It then verifies by magic bytes and strips `data:<mime>;base64,` prefixes.

---

## 14. Size and Timeout Limits

| Limit | Value | Purpose |
|---|---|---|
| `MAX_WORKLOAD_BYTES` | 64 MB | Cap on workload response body read |
| `MAX_PROBE_BYTES` | 2 MB | Cap on health probe and latency sample response body |
| `MAX_SNIPPET` | 1000 chars | Truncation limit for text snippets in reports and console |
| `_DOWN_PHASE_TIMEOUT` | 15 s | Max time waiting for old service to stop (Phase 1) |
| `_DOWN_PHASE_POLL` | 1 s | Poll interval during Phase 1 |
| `timeouts.readiness_seconds` | 900 s | Max time waiting for new service to become healthy (Phase 2) |
| `timeouts.http_seconds` | 300 s | Per-request HTTP timeout (covers large model inference) |
| `timeouts.socket_seconds` | 10 s | TCP connect+read for switcher ports |

---

## 15. Output Files

All output is written to the same directory as the script (`test/`):

```
test/
  workload_<stamp>_<service-name>.<ext>   # one artifact per passing service
  workload_report_<stamp>.json            # full machine-readable report
  workload_report_<stamp>.txt             # human-readable summary
```

`<stamp>` format: `YYYYMMDD_HHMMSSz` in UTC (e.g. `20260515_195653Z`).

Exit code: `0` if all tested services passed, `1` if any failed, `2` if configuration error.
