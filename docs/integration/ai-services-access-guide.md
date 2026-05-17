# AI Services Access Guide

This node exposes AI services on a single shared port (`192.168.8.5:30000`).
Only one service is active at a time. The **service switcher** manages which
service owns the port and handles GPU lane transitions.

---

## How to Activate a Service

Send a start command to the switcher command port:

```bash
echo "start <service-name>" | nc 192.168.8.5 20100
```

Check which service is currently active:

```bash
nc 192.168.8.5 30100
```

Available service names (all 24):

```
image-flux          image-qwen          image-sdxl          image-sdxl-turbo
tts-coqui           tts-f5              tts-qwen3-clone     tts-qwen3-design     tts-qwen3-studio
video-animatediff   video-ltx           video-svd
llm-gpt120b         llm-gpt20b          llm-llama70b        llm-mixtral-llama70b
llm-mixtral8x22b    llm-nemotron-nano   llm-nemotron-super  llm-qwen327b         llm-wizardlm8x22b
translator-accurate translator-fast     translator-medium
```

---

## Service Endpoints

All services respond on `http://192.168.8.5:30000`.

---

### image-sdxl

**Model:** Stable Diffusion XL Base 1.0 (NVIDIA GPU)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/generate` | Generate an image |
| `GET` | `/health` | Liveness probe |

**Request body (`/generate`):**

```json
{
  "prompt": "A serene Japanese garden, cherry blossoms, koi pond",
  "negative_prompt": "blurry, watermark",
  "width": 1024,
  "height": 1024,
  "steps": 25
}
```

**Response:** Raw `image/png` bytes (save directly to a file).

**Example:**

```bash
echo "start image-sdxl" | nc 192.168.8.5 20100
curl -X POST http://192.168.8.5:30000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a red apple on a white table","width":1024,"height":1024,"steps":25}' \
  -o output.png
```

---

### tts-qwen3-clone

**Model:** Qwen3-TTS Voice-Design 1.7B (NVIDIA GPU)

Voices are generated on the fly from natural-language descriptions — no fixed
speaker roster or reference audio required.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/audio/speech` | Synthesise speech (OpenAI-compatible) |
| `POST` | `/v1/tts/voice-clone` | Synthesise with a named narrator |
| `GET` | `/v1/tts/narrators` | List available narrators |
| `GET` | `/health` | Liveness probe |

**Request body (`/v1/audio/speech`):**

```json
{
  "input": "Hello, this is a test.",
  "lang": "en",
  "voice": "optional: free-text voice description",
  "mood": "neutral"
}
```

Field `input` is **required**. `lang` defaults to `en`.
Available mood values: `neutral` (and narrator-specific moods via `/v1/tts/narrators`).

**Response:** Raw audio bytes (`audio/wav` or `audio/mp3`).

**Example:**

```bash
echo "start tts-qwen3-clone" | nc 192.168.8.5 20100
curl -X POST http://192.168.8.5:30000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Welcome to the AI service node.","lang":"en"}' \
  -o speech.wav
```

**Using a named narrator** (`/v1/tts/voice-clone`):

```bash
# List narrators first
curl http://192.168.8.5:30000/v1/tts/narrators

# Available narrators: arthur, diane, ethan, grant, maya, ruth
curl -X POST http://192.168.8.5:30000/v1/tts/voice-clone \
  -H "Content-Type: application/json" \
  -d '{"text":"Good morning.","narrator":"arthur","mood":"neutral","lang":"en"}' \
  -o voice.wav
```

---

### translator-accurate

**Model:** Aya Expanse 32B Q3_K_M (AMD GPU)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/translate` | Translate text |
| `GET` | `/health` | Liveness probe |

**Request body (`/v1/translate`):**

```json
{
  "text": "Artificial intelligence is transforming the world.",
  "src_lang": "en",
  "tgt_lang": "fr"
}
```

All three fields are **required**. Use ISO 639-1 language codes (`en`, `fr`, `de`, `es`, `it`, `pt`, `zh`, `ja`, etc.).

**Response:**

```json
{
  "translated_text": "L'intelligence artificielle transforme le monde.",
  "src_lang": "en",
  "tgt_lang": "fr",
  "chunks": 1,
  "model": "translator-accurate"
}
```

**Example:**

```bash
echo "start translator-accurate" | nc 192.168.8.5 20100
curl -X POST http://192.168.8.5:30000/v1/translate \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello world","src_lang":"en","tgt_lang":"es"}'
```

---

### llm-qwen327b

**Model:** Qwen3-27B (AMD GPU) — llama-server, OpenAI-compatible API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/chat/completions` | Chat inference |
| `GET` | `/health` | Liveness probe |
| `GET` | `/v1/models` | List available models |

**Request body (`/v1/chat/completions`):**

```json
{
  "model": "qwen3-27b",
  "messages": [
    {"role": "user", "content": "Explain transformer attention in one paragraph."}
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

**Response:** Standard OpenAI chat completion JSON.

**Example:**

```bash
echo "start llm-qwen327b" | nc 192.168.8.5 20100
curl -X POST http://192.168.8.5:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-27b",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "max_tokens": 64
  }'
```

---

### llm-mixtral8x22b

**Model:** Mixtral-8x22B-v0.1 Q5_K_S (AMD GPU) — ik_llama.cpp (llama-server fork), OpenAI-compatible API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/chat/completions` | Chat inference |
| `GET` | `/health` | Liveness probe |
| `GET` | `/v1/models` | List available models |

**Request body (`/v1/chat/completions`):**

```json
{
  "messages": [
    {"role": "user", "content": "Write a Python binary search function with type hints."}
  ],
  "temperature": 0.2,
  "max_tokens": 400
}
```

**Response:** Standard OpenAI chat completion JSON.

**Example:**

```bash
echo "start llm-mixtral8x22b" | nc 192.168.8.5 20100
curl -X POST http://192.168.8.5:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "max_tokens": 64,
    "temperature": 0.2
  }'
```

**Notes:** Mixture-of-Experts (8×22B) architecture. Best suited for code generation and structured tasks at low temperature (`0.1`–`0.3`). Uses `mistral` chat template.

---

## Notes

- **GPU lanes:** `image-sdxl` and `tts-qwen3-clone` share the NVIDIA GPU.
  `translator-accurate`, `llm-qwen327b`, and `llm-mixtral8x22b` share the AMD GPU.
  Switching between lanes (NVIDIA ↔ AMD) takes a few extra seconds.
- **Warmup time:** After a switch the new service may take 10–30 seconds to load
  its model before `/health` returns 200.
- **Service port:** All services bind to port `30000`. Only one can be active at
  a time.
- **Command port:** `20100` (TCP, plain text).
- **Status port:** `30100` (TCP, plain text).
