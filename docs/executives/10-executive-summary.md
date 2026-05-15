# Executive Summary — AI Inference Node

**Audience:** Leadership, stakeholders  
**Last updated:** 2026-05-15

---

## What this is

A single Linux server at `192.168.8.5` running 24 specialized AI inference services. The node is managed by a lightweight coordinator called **service-switcher** that activates exactly one service at a time on demand, keeping resource usage low while providing access to a broad model library over a local network.

---

## Capabilities

| Category | Services available |
|---|---|
| Image generation | FLUX, Qwen, SDXL, SDXL-Turbo |
| Text-to-speech | Coqui, F5-TTS, Qwen3 (clone / design / studio) |
| Video generation | AnimateDiff, LTX-Video, SVD |
| Large language models | GPT-120B, GPT-20B, LLaMA-70B, Mixtral-8x22B, Mixtral+LLaMA-70B, Nemotron-Nano, Nemotron-Super, Qwen3-27B, WizardLM-8x22B |
| Translation | Accurate (EN→FR), Fast (EN→ES), Medium (EN→DE) |

Total: **24 services** across 4 AI modalities.

---

## How it works (non-technical)

1. A client sends a short text message (e.g. `start image-sdxl`) to the coordinator.
2. The coordinator activates the requested AI service via the OS.
3. The client waits until the service is healthy (verified via a health check).
4. The client sends inference requests directly to the service over HTTP.
5. When a different service is needed, the process repeats — the previous service is stopped automatically.

---

## Key operational constraints

- **One service at a time.** Only one AI service can run on any GPU lane at once; switching takes 10–900 seconds depending on model size.
- **Voice files required for TTS.** The five text-to-speech services will return errors until speaker reference audio files are installed on the node.
- **service-stopper required for cross-lane switches.** Switching from an image/TTS/video service to an LLM service (or vice versa) requires a helper systemd unit (`service-stopper`) to be running.
- **LAN-only access.** No authentication is implemented; the node should only be accessible from trusted network segments.

---

## Evidence

- Source: [main.go](../../main.go)
- Service registry: [services.json](../../services.json)
- Full endpoint config: [test/lan_workload_test_config.json](../../test/lan_workload_test_config.json)

---

## Open questions / not verified

- GPU hardware inventory (NVIDIA and AMD card models) — not confirmed from code
- Storage capacity and model file locations — not verified from code
- Network firewall / VLAN segmentation — not verified
