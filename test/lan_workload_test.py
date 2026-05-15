#!/usr/bin/env python3
"""LAN workload quality tester for service_switcher.

For each configured service (in group order):
  1. Sends "start <service>" to the switcher command port
  2. Polls the service endpoint until it responds (readiness probe)
  3. Sends a real workload request and saves the produced artifact
     (image, audio, video, or text) next to this script
  4. Runs latency samples using the readiness probe payload
  5. Writes a JSON report and a human-readable text report

Run from any host with network access to the switcher and endpoints:

    python lan_workload_test.py \\
        [--config test/lan_workload_test_config.json] \\
        [--groups amd] \\
        [--services image-flux tts-f5]
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import socket
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib import error, request as urllib_request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_WORKLOAD_BYTES = 64 * 1024 * 1024   # 64 MB cap for workload responses
MAX_PROBE_BYTES = 2 * 1024 * 1024       # 2 MB cap for readiness probe responses
MAX_SNIPPET = 1000                       # characters shown in report for text/JSON

# How long to wait for the old service to stop before polling for the new one.
# Prevents the health poll from immediately catching the old service on port 30000.
_DOWN_PHASE_TIMEOUT = 15.0   # seconds to wait for health to go DOWN
_DOWN_PHASE_POLL    = 1.0    # poll interval during down-phase


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def slugify(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    return clean.strip("-.") or "sample"


def extension_for_content_type(content_type: str) -> str:
    ct = content_type.lower().split(";")[0].strip()
    if ct == "application/json":
        return ".json"
    if ct.startswith("text/"):
        return ".txt"
    if ct in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if ct == "image/png":
        return ".png"
    if ct == "image/webp":
        return ".webp"
    if ct == "image/gif":
        return ".gif"
    if ct.startswith("image/"):
        subtype = ct.split("/", 1)[1]
        return f".{subtype}" if subtype else ".img"
    if ct in {"audio/mpeg", "audio/mp3"}:
        return ".mp3"
    if ct == "audio/wav":
        return ".wav"
    if ct == "audio/ogg":
        return ".ogg"
    if ct == "audio/flac":
        return ".flac"
    if ct.startswith("audio/"):
        subtype = ct.split("/", 1)[1]
        return f".{subtype}" if subtype else ".audio"
    if ct in {"video/mp4"}:
        return ".mp4"
    if ct.startswith("video/"):
        subtype = ct.split("/", 1)[1]
        return f".{subtype}" if subtype else ".video"
    return ".bin"


def detect_mime_from_bytes(data: bytes) -> Optional[str]:
    """Identify MIME type from magic bytes."""
    if len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    if data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:4] == b"fLaC":
        return "audio/flac"
    return None


def extract_embedded_artifact(
    json_bytes: bytes,
) -> Tuple[Optional[bytes], Optional[str]]:
    """Try to extract a base64-encoded binary artifact from a JSON response.

    Checks common field names used by AI inference APIs.
    Returns (raw_bytes, mime_type) or (None, None) if not found.
    """
    try:
        obj = json.loads(json_bytes.decode("utf-8", errors="replace"))
    except Exception:
        return None, None

    for key in ("image", "audio", "video", "data", "result", "output", "content", "file"):
        val = obj.get(key)
        if not isinstance(val, str) or len(val) < 64:
            continue
        # Strip data-URI prefix if present
        raw_b64 = val
        if val.startswith("data:") and ";base64," in val:
            raw_b64 = val.split(";base64,", 1)[1]
        try:
            decoded = base64.b64decode(raw_b64, validate=False)
        except Exception:
            continue
        mime = detect_mime_from_bytes(decoded)
        if mime:
            return decoded, mime

    return None, None


def quantile_nearest_rank(values: List[float], q: float) -> float:
    if not values:
        return math.nan
    if q <= 0.0:
        return min(values)
    if q >= 1.0:
        return max(values)
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


# ---------------------------------------------------------------------------
# Network transport
# ---------------------------------------------------------------------------

def send_switch_command(
    host: str,
    port: int,
    service_name: str,
    timeout: float,
) -> Dict[str, Any]:
    cmd = f"start {service_name}\n".encode("utf-8")
    t0 = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout) as conn:
        conn.sendall(cmd)
        conn.settimeout(timeout)
        data = conn.recv(256)
    elapsed = time.perf_counter() - t0
    response = data.decode("utf-8", errors="replace").strip()
    return {
        "ok": response == "ok",
        "response": response,
        "elapsed_seconds": round(elapsed, 3),
    }


def read_switcher_status(host: str, port: int, timeout: float) -> Dict[str, Any]:
    with socket.create_connection((host, port), timeout=timeout) as conn:
        conn.settimeout(timeout)
        data = conn.recv(4096)
    text = data.decode("utf-8", errors="replace").strip()
    try:
        return json.loads(text) if text else {}
    except Exception:
        return {"raw": text}


def http_request(
    url: str,
    method: str,
    payload: Optional[Dict[str, Any]],
    http_timeout: float,
    max_bytes: int,
) -> Dict[str, Any]:
    """Send an HTTP request and return a structured result dict."""
    body: Optional[bytes] = None
    headers: Dict[str, str] = {"Accept": "*/*"}

    if method == "POST" and payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib_request.Request(url=url, data=body, method=method, headers=headers)
    t0 = time.perf_counter()

    try:
        with urllib_request.urlopen(req, timeout=http_timeout) as resp:
            resp_bytes = resp.read(max_bytes)
            status_code: Optional[int] = getattr(resp, "status", 200)
            content_type = str(resp.headers.get("Content-Type", "application/octet-stream"))
            final_url = str(getattr(resp, "url", url))
        ok_transport = True
        ok_status = True

    except error.HTTPError as exc:
        resp_bytes = exc.read(MAX_PROBE_BYTES)
        status_code = exc.code
        content_type = (
            str(exc.headers.get("Content-Type", "application/octet-stream"))
            if exc.headers
            else "application/octet-stream"
        )
        final_url = url
        ok_transport = True
        ok_status = False

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return {
            "ok": False,
            "transport_ok": False,
            "status_code": None,
            "content_type": "application/octet-stream",
            "response_bytes": b"",
            "snippet": str(exc)[:MAX_SNIPPET],
            "elapsed_seconds": round(elapsed, 3),
            "final_url": url,
        }

    elapsed = time.perf_counter() - t0
    snippet = resp_bytes.decode("utf-8", errors="replace")[:MAX_SNIPPET] if resp_bytes else ""

    return {
        "ok": ok_transport and ok_status,
        "transport_ok": ok_transport,
        "status_code": status_code,
        "content_type": content_type,
        "response_bytes": resp_bytes,
        "snippet": snippet,
        "elapsed_seconds": round(elapsed, 3),
        "final_url": final_url,
    }


# ---------------------------------------------------------------------------
# Readiness polling
# ---------------------------------------------------------------------------

def poll_readiness(
    health_url: str,
    expected_codes: List[int],
    http_timeout: float,
    readiness_timeout: float,
    poll_interval: float,
) -> Tuple[bool, float, Dict[str, Any]]:
    """Poll GET /health with two-phase down→up detection.

    Phase 1 (down): poll every _DOWN_PHASE_POLL seconds for up to _DOWN_PHASE_TIMEOUT
                    seconds, waiting for health to fail (old service stopped via
                    systemd Conflicts=).  If health stays up the whole window, assume
                    we are already on the right service and skip the wait.
    Phase 2 (up):   poll at poll_interval for up to readiness_timeout seconds, waiting
                    for health to return an expected status code (new service ready).

    Returns (ready, total_elapsed_seconds, last_response_dict).
    """
    t0 = time.perf_counter()
    last: Dict[str, Any] = {}
    attempt = 0

    # ------------------------------------------------------------------
    # Phase 1: wait for old service to go DOWN
    # ------------------------------------------------------------------
    print(f"  waiting for old service to stop (up to {_DOWN_PHASE_TIMEOUT:.0f}s) ...")
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= _DOWN_PHASE_TIMEOUT:
            print(f"  old service did not stop within {_DOWN_PHASE_TIMEOUT:.0f}s — assuming correct service")
            break

        resp = http_request(health_url, "GET", None, http_timeout, MAX_PROBE_BYTES)
        attempt += 1

        if not resp["transport_ok"] or resp["status_code"] not in expected_codes:
            elapsed = time.perf_counter() - t0
            print(f"  old service down after {elapsed:.1f}s — waiting for new service ...")
            break

        time.sleep(_DOWN_PHASE_POLL)

    # ------------------------------------------------------------------
    # Phase 2: wait for new service to come UP
    # ------------------------------------------------------------------
    print(f"  polling GET {health_url} (timeout={readiness_timeout:.0f}s, interval={poll_interval:.0f}s) ...")
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= readiness_timeout:
            print(f"    [attempt {attempt}] TIMEOUT after {elapsed:.0f}s — service did not become ready")
            return False, elapsed, last

        resp = http_request(health_url, "GET", None, http_timeout, MAX_PROBE_BYTES)
        last = resp
        attempt += 1

        if resp["transport_ok"] and resp["status_code"] in expected_codes:
            elapsed = time.perf_counter() - t0
            print(f"    [attempt {attempt}] READY after {elapsed:.1f}s — HTTP {resp['status_code']}")
            return True, elapsed, resp

        if resp["status_code"] is not None:
            info = f"HTTP {resp['status_code']}"
        else:
            info = f"no response: {resp['snippet'][:80]}"
        elapsed = time.perf_counter() - t0
        print(f"    [attempt {attempt}] {elapsed:.0f}s elapsed — {info}, retrying in {poll_interval:.0f}s ...")
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Artifact saving
# ---------------------------------------------------------------------------

def resolve_artifact(
    response_bytes: bytes,
    declared_content_type: str,
) -> Tuple[bytes, str]:
    """Return (artifact_bytes, resolved_content_type).

    If the declared content type is JSON, tries to extract an embedded
    binary artifact (base64). Falls back to the raw bytes.
    """
    ct_lower = declared_content_type.lower().split(";")[0].strip()

    if "json" in ct_lower and response_bytes:
        extracted, extracted_mime = extract_embedded_artifact(response_bytes)
        if extracted and extracted_mime:
            return extracted, extracted_mime

    # Check magic bytes when content-type is generic or octet-stream
    if ct_lower in ("application/octet-stream", "") and response_bytes:
        detected = detect_mime_from_bytes(response_bytes)
        if detected:
            return response_bytes, detected

    return response_bytes, declared_content_type.split(";")[0].strip()


def save_artifact(
    script_dir: Path,
    service_name: str,
    data: bytes,
    content_type: str,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    ext = extension_for_content_type(content_type)
    filename = f"workload_{stamp}_{slugify(service_name)}{ext}"
    path = script_dir / filename
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# Per-service test
# ---------------------------------------------------------------------------

def run_service_test(
    *,
    service_name: str,
    group: str,
    service_type: str,
    endpoint_url: str,
    health_url: str,
    method: str,
    readiness_payload: Optional[Dict[str, Any]],
    workload_payload: Optional[Dict[str, Any]],
    expected_codes: List[int],
    quality_criteria: str,
    notes: str,
    switcher_host: str,
    command_port: int,
    status_port: int,
    socket_timeout: float,
    http_timeout: float,
    readiness_timeout: float,
    poll_interval: float,
    latency_requests: int,
    script_dir: Path,
) -> Dict[str, Any]:
    """Execute the full test cycle for one service and return a result dict."""

    result: Dict[str, Any] = {
        "service_name": service_name,
        "group": group,
        "endpoint_url": endpoint_url,
        "switch_ok": False,
        "switch_response": "",
        "switch_elapsed_seconds": 0.0,
        "status_snapshot": {},
        "warmup_seconds": None,
        "workload_ok": False,
        "workload_status_code": None,
        "workload_content_type": None,
        "workload_elapsed_seconds": 0.0,
        "workload_snippet": "",
        "artifact_path": None,
        "artifact_size_bytes": None,
        "artifact_content_type": None,
        "latency_seconds": {},
        "latency_sample_count": 0,
        "quality_criteria": quality_criteria,
        "notes": notes,
        "result": "failed",
        "message": "",
    }

    # ------------------------------------------------------------------
    # 1. Switch
    # ------------------------------------------------------------------
    print(f"[{service_name}] switching service via {switcher_host}:{command_port}")
    try:
        switch = send_switch_command(switcher_host, command_port, service_name, socket_timeout)
    except Exception as exc:
        switch = {"ok": False, "response": str(exc), "elapsed_seconds": 0.0}

    result["switch_ok"] = switch["ok"]
    result["switch_response"] = switch["response"]
    result["switch_elapsed_seconds"] = switch["elapsed_seconds"]
    print(f"  switch: ok={switch['ok']}  response={switch['response']!r}  elapsed={switch['elapsed_seconds']}s")

    if not switch["ok"]:
        result["message"] = f"switcher rejected command: {switch['response']!r}"
        return result

    # ------------------------------------------------------------------
    # 2. Switcher status snapshot
    # ------------------------------------------------------------------
    try:
        result["status_snapshot"] = read_switcher_status(switcher_host, status_port, socket_timeout)
    except Exception as exc:
        result["status_snapshot"] = {"error": str(exc)}

    # ------------------------------------------------------------------
    # 3. Readiness polling
    # ------------------------------------------------------------------
    probe = readiness_payload if readiness_payload is not None else workload_payload
    ready, warmup_elapsed, ready_resp = poll_readiness(
        health_url=health_url,
        expected_codes=expected_codes,
        http_timeout=http_timeout,
        readiness_timeout=readiness_timeout,
        poll_interval=poll_interval,
    )
    result["warmup_seconds"] = round(warmup_elapsed, 3)
    print(f"  ready={ready}  warmup={round(warmup_elapsed, 1)}s")

    if not ready:
        result["message"] = f"readiness timeout after {round(warmup_elapsed, 1)}s"
        return result

    # ------------------------------------------------------------------
    # 4. Real workload request
    # ------------------------------------------------------------------
    print(f"  sending workload request ...")
    workload_resp = http_request(
        url=endpoint_url,
        method=method,
        payload=workload_payload,
        http_timeout=http_timeout,
        max_bytes=MAX_WORKLOAD_BYTES,
    )

    workload_ok = workload_resp["transport_ok"] and workload_resp["status_code"] in expected_codes
    result["workload_ok"] = workload_ok
    result["workload_status_code"] = workload_resp["status_code"]
    result["workload_content_type"] = workload_resp["content_type"]
    result["workload_elapsed_seconds"] = workload_resp["elapsed_seconds"]
    result["workload_snippet"] = workload_resp["snippet"]

    print(
        f"  workload: ok={workload_ok}  status={workload_resp['status_code']}"
        f"  ct={workload_resp['content_type']}  elapsed={workload_resp['elapsed_seconds']}s"
    )

    # ------------------------------------------------------------------
    # 5. Save artifact
    # ------------------------------------------------------------------
    if workload_ok and workload_resp["response_bytes"]:
        artifact_bytes: Optional[bytes] = None
        artifact_ct: Optional[str] = None

        # LLM: extract generated text from choices[0].message.content
        if service_type == "llm":
            try:
                obj = json.loads(workload_resp["response_bytes"].decode("utf-8", errors="replace"))
                choices = obj.get("choices", [])
                if choices:
                    text = (
                        choices[0].get("message", {}).get("content", "")
                        or choices[0].get("text", "")
                    )
                    if text:
                        artifact_bytes = text.encode("utf-8")
                        artifact_ct = "text/plain"
                        result["workload_snippet"] = text[:MAX_SNIPPET]
            except Exception as exc:
                print(f"  WARNING: could not extract LLM text: {exc}")

        # Translator: extract translated_text from JSON
        elif service_type == "translator":
            try:
                obj = json.loads(workload_resp["response_bytes"].decode("utf-8", errors="replace"))
                translated = obj.get("translated_text", "")
                if translated:
                    artifact_bytes = translated.encode("utf-8")
                    artifact_ct = "text/plain"
                    result["workload_snippet"] = translated[:MAX_SNIPPET]
            except Exception as exc:
                print(f"  WARNING: could not extract translation: {exc}")

        # Image / TTS / video / unknown: use binary/base64 detection
        if artifact_bytes is None:
            artifact_bytes, artifact_ct = resolve_artifact(
                workload_resp["response_bytes"],
                workload_resp["content_type"],
            )

        try:
            artifact_path = save_artifact(script_dir, service_name, artifact_bytes, artifact_ct or "application/octet-stream")
            result["artifact_path"] = str(artifact_path)
            result["artifact_size_bytes"] = len(artifact_bytes)
            result["artifact_content_type"] = artifact_ct
            print(f"  artifact: {artifact_path.name}  ({len(artifact_bytes):,} bytes)  [{artifact_ct}]")
        except Exception as exc:
            print(f"  WARNING: could not save artifact: {exc}")

    # ------------------------------------------------------------------
    # 6. Latency samples (using lightweight probe payload)
    # ------------------------------------------------------------------
    latencies: List[float] = [workload_resp["elapsed_seconds"]]
    for _ in range(latency_requests):
        lat_resp = http_request(
            url=endpoint_url,
            method=method,
            payload=probe,
            http_timeout=http_timeout,
            max_bytes=MAX_PROBE_BYTES,
        )
        latencies.append(lat_resp["elapsed_seconds"])

    result["latency_sample_count"] = len(latencies)
    result["latency_seconds"] = {
        "min": round(min(latencies), 3),
        "max": round(max(latencies), 3),
        "avg": round(statistics.fmean(latencies), 3),
        "p50": round(quantile_nearest_rank(latencies, 0.50), 3),
        "p95": round(quantile_nearest_rank(latencies, 0.95), 3),
        "p99": round(quantile_nearest_rank(latencies, 0.99), 3),
    }
    print(
        f"  latency ({len(latencies)} samples): "
        f"avg={result['latency_seconds']['avg']}s  "
        f"p50={result['latency_seconds']['p50']}s  "
        f"p95={result['latency_seconds']['p95']}s"
    )

    # ------------------------------------------------------------------
    # 7. Pass/fail
    # ------------------------------------------------------------------
    if workload_ok:
        result["result"] = "passed"
        result["message"] = "ok"
    else:
        result["message"] = (
            f"workload request failed: status={workload_resp['status_code']}"
        )

    return result


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

def write_reports(script_dir: Path, report: Dict[str, Any]) -> Tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    json_path = script_dir / f"workload_report_{stamp}.json"
    txt_path = script_dir / f"workload_report_{stamp}.txt"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = report["summary"]
    lines: List[str] = [
        f"timestamp_utc:   {report['timestamp_utc']}",
        f"config_path:     {report['config_path']}",
        f"command_address: {report['command_address']}",
        f"active_groups:   {', '.join(report['active_groups'])}",
        "",
        (
            f"summary:  total={summary['total']}  "
            f"passed={summary['passed']}  failed={summary['failed']}  "
            f"artifacts_saved={summary['artifacts_saved']}"
        ),
        "",
    ]

    for r in report["results"]:
        lines.append(f"{'='*60}")
        lines.append(f"service:  {r['service_name']}  [{r['group']}]")
        lines.append(f"endpoint: {r['endpoint_url']}")
        lines.append(
            f"switch:   ok={r['switch_ok']}  "
            f"response={r['switch_response']!r}  "
            f"elapsed={r['switch_elapsed_seconds']}s"
        )
        lines.append(f"warmup:   {r.get('warmup_seconds')}s")
        lines.append(
            f"workload: ok={r['workload_ok']}  "
            f"status={r['workload_status_code']}  "
            f"elapsed={r['workload_elapsed_seconds']}s  "
            f"content_type={r['workload_content_type']}"
        )

        if r.get("artifact_path"):
            pname = Path(r["artifact_path"]).name
            lines.append(
                f"artifact: {pname}  "
                f"({r.get('artifact_size_bytes', 0):,} bytes)  "
                f"[{r.get('artifact_content_type')}]"
            )
        else:
            lines.append("artifact: none")

        lat = r.get("latency_seconds", {})
        if lat:
            lines.append(
                f"latency:  min={lat.get('min')}s  avg={lat.get('avg')}s  "
                f"p50={lat.get('p50')}s  p95={lat.get('p95')}s  p99={lat.get('p99')}s  "
                f"[{r['latency_sample_count']} samples]"
            )

        if r.get("quality_criteria"):
            lines.append(f"quality:  {r['quality_criteria']}")

        lines.append(f"result:   {r['result']}  |  {r['message']}")

        if r.get("workload_snippet") and not r["workload_ok"]:
            lines.append(f"error:    {r['workload_snippet'][:400]}")
        elif r.get("workload_snippet") and r["workload_ok"]:
            # Show text snippet for readable responses (LLM, translator)
            ct = (r.get("workload_content_type") or "").lower()
            if any(t in ct for t in ("json", "text")):
                snippet = r["workload_snippet"][:400]
                if snippet:
                    lines.append(f"response: {snippet}")

        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LAN workload quality tester for service_switcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python lan_workload_test.py\n"
            "  python lan_workload_test.py --groups amd\n"
            "  python lan_workload_test.py --services image-flux tts-f5\n"
        ),
    )
    parser.add_argument(
        "--config",
        default="test/lan_workload_test_config.json",
        help="Path to workload test config JSON (default: test/lan_workload_test_config.json)",
    )
    parser.add_argument(
        "--groups",
        nargs="*",
        metavar="GROUP",
        help="Run only services in these groups, e.g. --groups amd",
    )
    parser.add_argument(
        "--services",
        nargs="*",
        metavar="NAME",
        help="Run only these specific service names, e.g. --services image-flux tts-f5",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config).expanduser().resolve()

    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}")
        return 2

    cfg: Dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))

    switcher_host = str(cfg.get("switcher_host", "127.0.0.1"))
    command_port = int(cfg.get("command_port", 20100))
    status_port = int(cfg.get("status_port", 30100))

    timeout_cfg = cfg.get("timeouts", {})
    socket_timeout = float(timeout_cfg.get("socket_seconds", 10.0))
    http_timeout = float(timeout_cfg.get("http_seconds", 300.0))
    readiness_timeout = float(timeout_cfg.get("readiness_seconds", 900.0))
    poll_interval = float(cfg.get("poll_interval_seconds", 3.0))
    latency_requests = int(cfg.get("latency_requests", 3))

    health_base_url = str(cfg.get("health_base_url", f"http://{switcher_host}:30000"))
    health_url = health_base_url.rstrip("/") + "/health"

    group_order: List[str] = [str(g).lower() for g in cfg.get("group_order", ["nvidia", "amd"])]
    selected_groups: Optional[List[str]] = (
        [g.lower() for g in args.groups] if args.groups else None
    )
    selected_services: Optional[List[str]] = (
        list(args.services) if args.services else None
    )
    active_groups = selected_groups or group_order

    # Warn if service-stopper is not running — cross-lane transitions will hang
    try:
        sp = subprocess.run(
            ["systemctl", "is-active", "service-stopper.service"],
            capture_output=True, text=True, timeout=5,
        )
        if sp.stdout.strip() != "active":
            print("WARNING: service-stopper.service is NOT active on this host.")
            print("         LLM<->NVIDIA service transitions (llm<->tts/image/video) require")
            print("         service-stopper to stop the old service before the new one can")
            print("         bind port 30000.  Translator services have full cross-lane")
            print("         Conflicts= and do not need service-stopper.")
            print("         Start it with: sudo systemctl start service-stopper.service")
            print()
    except Exception:
        pass  # Not running on the AI node — skip check

    service_tests: List[Dict[str, Any]] = cfg.get("service_tests", [])
    if not service_tests:
        print("ERROR: no service_tests in config")
        return 2

    # Build ordered list respecting group_order
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for test in service_tests:
        g = str(test.get("group", "")).lower()
        by_group.setdefault(g, []).append(test)

    ordered_tests: List[Dict[str, Any]] = []
    for g in active_groups:
        ordered_tests.extend(
            sorted(by_group.get(g, []), key=lambda t: str(t.get("service_name", "")))
        )

    if selected_services:
        ordered_tests = [t for t in ordered_tests if t.get("service_name") in selected_services]

    if not ordered_tests:
        print(f"ERROR: no matching tests for groups={active_groups} services={selected_services}")
        return 2

    print(
        f"Workload test: {len(ordered_tests)} service(s)  "
        f"command={switcher_host}:{command_port}  "
        f"readiness_timeout={readiness_timeout}s"
    )

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "command_address": f"{switcher_host}:{command_port}",
        "status_address": f"{switcher_host}:{status_port}",
        "active_groups": active_groups,
        "selected_services": selected_services,
        "results": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "artifacts_saved": 0,
        },
    }

    for test in ordered_tests:
        service_name = str(test.get("service_name", ""))
        group = str(test.get("group", ""))
        service_type = str(test.get("service_type", "unknown"))
        endpoint_url = str(test.get("endpoint_url", ""))
        method = str(test.get("method", "POST")).upper()
        readiness_payload: Optional[Dict[str, Any]] = test.get("readiness_payload")
        workload_payload: Optional[Dict[str, Any]] = test.get("workload_payload")
        expected_codes: List[int] = list(test.get("expected_status_codes", [200]))
        quality_criteria = str(test.get("quality_criteria", ""))
        notes = str(test.get("notes", ""))

        print(f"\n{'─'*60}")

        result = run_service_test(
            service_name=service_name,
            group=group,
            service_type=service_type,
            endpoint_url=endpoint_url,
            health_url=health_url,
            method=method,
            readiness_payload=readiness_payload,
            workload_payload=workload_payload,
            expected_codes=expected_codes,
            quality_criteria=quality_criteria,
            notes=notes,
            switcher_host=switcher_host,
            command_port=command_port,
            status_port=status_port,
            socket_timeout=socket_timeout,
            http_timeout=http_timeout,
            readiness_timeout=readiness_timeout,
            poll_interval=poll_interval,
            latency_requests=latency_requests,
            script_dir=script_dir,
        )

        report["results"].append(result)
        if result["result"] == "passed":
            report["summary"]["passed"] += 1
        else:
            report["summary"]["failed"] += 1
        if result.get("artifact_path"):
            report["summary"]["artifacts_saved"] += 1

    report["summary"]["total"] = len(report["results"])

    print(f"\n{'='*60}")
    s = report["summary"]
    print(
        f"Done:  total={s['total']}  passed={s['passed']}  "
        f"failed={s['failed']}  artifacts={s['artifacts_saved']}"
    )

    json_path, txt_path = write_reports(script_dir, report)
    print(f"JSON report: {json_path}")
    print(f"Text report: {txt_path}")

    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
