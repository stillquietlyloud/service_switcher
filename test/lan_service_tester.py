#!/usr/bin/env python3
"""Portable LAN service tester for service_switcher.

This script:
1. Reads switcher command/status addresses from services.json.
2. Sends "start <service>\n" to the switcher command port.
3. Waits a fixed 60 seconds.
4. Sends a POST request to each service endpoint (hardcoded below).
5. Writes JSON and text reports next to this script.

No host-level commands are executed.
"""

from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import error, request
    
FIXED_WAIT_SECONDS = 60
SOCKET_TIMEOUT_SECONDS = 10
HTTP_TIMEOUT_SECONDS = 30
MAX_RESPONSE_SNIPPET = 800

# Hardcoded service tests. Keep this explicit and simple.
# Update endpoint_url and payload values for your environment.
SERVICE_TESTS: List[Dict[str, Any]] = [
    {"service_name": "image-flux", "endpoint_url": "http://192.168.8.5:30000/image-flux", "payload": {"ping": "image-flux"}},
    {"service_name": "image-qwen", "endpoint_url": "http://192.168.8.5:30000/image-qwen", "payload": {"ping": "image-qwen"}},
    {"service_name": "image-sdxl", "endpoint_url": "http://192.168.8.5:30000/image-sdxl", "payload": {"ping": "image-sdxl"}},
    {"service_name": "image-sdxl-turbo", "endpoint_url": "http://192.168.8.5:30000/image-sdxl-turbo", "payload": {"ping": "image-sdxl-turbo"}},
    {"service_name": "llm-gpt120b", "endpoint_url": "http://192.168.8.5:30000/llm-gpt120b", "payload": {"ping": "llm-gpt120b"}},
    {"service_name": "llm-gpt20b", "endpoint_url": "http://192.168.8.5:30000/llm-gpt20b", "payload": {"ping": "llm-gpt20b"}},
    {"service_name": "llm-llama70b", "endpoint_url": "http://192.168.8.5:30000/llm-llama70b", "payload": {"ping": "llm-llama70b"}},
    {"service_name": "llm-mixtral-llama70b", "endpoint_url": "http://192.168.8.5:30000/llm-mixtral-llama70b", "payload": {"ping": "llm-mixtral-llama70b"}},
    {"service_name": "llm-mixtral8x22b", "endpoint_url": "http://192.168.8.5:30000/llm-mixtral8x22b", "payload": {"ping": "llm-mixtral8x22b"}},
    {"service_name": "llm-nemotron-nano", "endpoint_url": "http://192.168.8.5:30000/llm-nemotron-nano", "payload": {"ping": "llm-nemotron-nano"}},
    {"service_name": "llm-nemotron-super", "endpoint_url": "http://192.168.8.5:30000/llm-nemotron-super", "payload": {"ping": "llm-nemotron-super"}},
    {"service_name": "llm-qwen327b", "endpoint_url": "http://192.168.8.5:30000/llm-qwen327b", "payload": {"ping": "llm-qwen327b"}},
    {"service_name": "llm-wizardlm8x22b", "endpoint_url": "http://192.168.8.5:30000/llm-wizardlm8x22b", "payload": {"ping": "llm-wizardlm8x22b"}},
    {"service_name": "translator-accurate", "endpoint_url": "http://192.168.8.5:30000/translator-accurate", "payload": {"ping": "translator-accurate"}},
    {"service_name": "translator-fast", "endpoint_url": "http://192.168.8.5:30000/translator-fast", "payload": {"ping": "translator-fast"}},
    {"service_name": "translator-medium", "endpoint_url": "http://192.168.8.5:30000/translator-medium", "payload": {"ping": "translator-medium"}},
    {"service_name": "tts-coqui", "endpoint_url": "http://192.168.8.5:30000/tts-coqui", "payload": {"ping": "tts-coqui"}},
    {"service_name": "tts-f5", "endpoint_url": "http://192.168.8.5:30000/tts-f5", "payload": {"ping": "tts-f5"}},
    {"service_name": "tts-qwen3-clone", "endpoint_url": "http://192.168.8.5:30000/tts-qwen3-clone", "payload": {"ping": "tts-qwen3-clone"}},
    {"service_name": "tts-qwen3-design", "endpoint_url": "http://192.168.8.5:30000/tts-qwen3-design", "payload": {"ping": "tts-qwen3-design"}},
    {"service_name": "tts-qwen3-studio", "endpoint_url": "http://192.168.8.5:30000/tts-qwen3-studio", "payload": {"ping": "tts-qwen3-studio"}},
    {"service_name": "video-animatediff", "endpoint_url": "http://192.168.8.5:30000/video-animatediff", "payload": {"ping": "video-animatediff"}},
    {"service_name": "video-ltx", "endpoint_url": "http://192.168.8.5:30000/video-ltx", "payload": {"ping": "video-ltx"}},
    {"service_name": "video-svd", "endpoint_url": "http://192.168.8.5:30000/video-svd", "payload": {"ping": "video-svd"}},
]


def parse_address(address: str) -> Tuple[str, int]:
    text = address.strip()
    if not text:
        raise ValueError("empty listen address")

    host, sep, port_text = text.rpartition(":")
    if sep == "" or not host or not port_text:
        raise ValueError(f"invalid listen address: {address}")

    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"invalid port in address: {address}") from exc

    return host, port


def read_switcher_config(config_path: Path) -> Dict[str, Any]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    command_address = raw.get("command_listen_address", "").strip()
    status_address = raw.get("status_listen_address", "").strip()
    services = raw.get("services", {})

    if not command_address or not status_address:
        raise ValueError("config must include command_listen_address and status_listen_address")
    if not isinstance(services, dict) or not services:
        raise ValueError("config must include at least one service")

    return raw


def send_switch_command(host: str, port: int, service_name: str) -> Dict[str, Any]:
    command = f"start {service_name}\n".encode("utf-8")
    started_at = time.perf_counter()

    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT_SECONDS) as conn:
        conn.sendall(command)
        conn.settimeout(SOCKET_TIMEOUT_SECONDS)
        data = conn.recv(256)

    elapsed = time.perf_counter() - started_at
    response = data.decode("utf-8", errors="replace").strip()
    return {
        "ok": response == "ok",
        "response": response,
        "elapsed_seconds": round(elapsed, 3),
    }


def read_switcher_status(host: str, port: int) -> Dict[str, Any]:
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT_SECONDS) as conn:
        conn.settimeout(SOCKET_TIMEOUT_SECONDS)
        data = conn.recv(4096)

    text = data.decode("utf-8", errors="replace").strip()
    parsed: Dict[str, Any] = json.loads(text) if text else {}
    return parsed


def http_post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
    )

    started_at = time.perf_counter()
    try:
        with request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            resp_body = resp.read(MAX_RESPONSE_SNIPPET)
            status_code = getattr(resp, "status", 200)
            ok = 200 <= status_code < 400
            snippet = resp_body.decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body_bytes = exc.read(MAX_RESPONSE_SNIPPET)
        status_code = exc.code
        ok = False
        snippet = body_bytes.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started_at
        return {
            "ok": False,
            "status_code": None,
            "response_snippet": str(exc),
            "elapsed_seconds": round(elapsed, 3),
        }

    elapsed = time.perf_counter() - started_at
    return {
        "ok": ok,
        "status_code": status_code,
        "response_snippet": snippet,
        "elapsed_seconds": round(elapsed, 3),
    }


def build_service_case_map() -> Dict[str, Dict[str, Any]]:
    return {entry["service_name"]: entry for entry in SERVICE_TESTS}


def write_reports(script_dir: Path, report: Dict[str, Any]) -> Tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    json_path = script_dir / f"report_{stamp}.json"
    txt_path = script_dir / f"report_{stamp}.txt"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append(f"timestamp_utc: {report['timestamp_utc']}")
    lines.append(f"config_path: {report['config_path']}")
    lines.append(f"command_address: {report['command_address']}")
    lines.append(f"status_address: {report['status_address']}")
    lines.append(f"fixed_wait_seconds: {report['fixed_wait_seconds']}")
    lines.append("")
    lines.append(
        "summary: "
        f"total={report['summary']['total']} "
        f"passed={report['summary']['passed']} "
        f"failed={report['summary']['failed']}"
    )
    lines.append("")

    for result in report["results"]:
        lines.append(f"service: {result['service_name']}")
        lines.append(f"switch_ok: {result['switch_ok']} response={result['switch_response']}")
        lines.append(
            "http_ok: "
            f"{result['http_ok']} status_code={result['http_status_code']} "
            f"elapsed={result['http_elapsed_seconds']}s"
        )
        lines.append(f"result: {result['result']}")
        lines.append(f"message: {result['message']}")
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable LAN tester for service_switcher")
    parser.add_argument(
        "--config",
        default="services.json",
        help="Path to services.json containing command/status listen addresses",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    config_path = Path(args.config).expanduser().resolve()

    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}")
        return 2

    try:
        config = read_switcher_config(config_path)
        command_host, command_port = parse_address(config["command_listen_address"])
        status_host, status_port = parse_address(config["status_listen_address"])
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: invalid config: {exc}")
        return 2

    service_case_map = build_service_case_map()
    configured_services = sorted(config["services"].keys())

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "command_address": config["command_listen_address"],
        "status_address": config["status_listen_address"],
        "fixed_wait_seconds": FIXED_WAIT_SECONDS,
        "results": [],
        "summary": {"total": 0, "passed": 0, "failed": 0},
    }

    for service_name in configured_services:
        case = service_case_map.get(service_name)
        if not case:
            result = {
                "service_name": service_name,
                "switch_ok": False,
                "switch_response": "not_sent",
                "switch_elapsed_seconds": 0.0,
                "status_snapshot": {},
                "wait_seconds": 0,
                "endpoint_url": "",
                "http_ok": False,
                "http_status_code": None,
                "http_response_snippet": "",
                "http_elapsed_seconds": 0.0,
                "result": "failed",
                "message": "missing hardcoded endpoint/payload case for service",
            }
            report["results"].append(result)
            report["summary"]["failed"] += 1
            continue

        print(f"[{service_name}] sending switch command...")
        try:
            switch_outcome = send_switch_command(command_host, command_port, service_name)
        except Exception as exc:  # noqa: BLE001
            switch_outcome = {
                "ok": False,
                "response": f"switch_error: {exc}",
                "elapsed_seconds": 0.0,
            }

        try:
            status_snapshot = read_switcher_status(status_host, status_port)
        except Exception as exc:  # noqa: BLE001
            status_snapshot = {"status_error": str(exc)}

        print(f"[{service_name}] waiting {FIXED_WAIT_SECONDS}s before POST...")
        time.sleep(FIXED_WAIT_SECONDS)

        print(f"[{service_name}] POST {case['endpoint_url']}")
        http_outcome = http_post_json(case["endpoint_url"], case["payload"])

        passed = bool(switch_outcome["ok"] and http_outcome["ok"])
        message = "ok" if passed else "switch or endpoint failed"

        result = {
            "service_name": service_name,
            "switch_ok": switch_outcome["ok"],
            "switch_response": switch_outcome["response"],
            "switch_elapsed_seconds": switch_outcome["elapsed_seconds"],
            "status_snapshot": status_snapshot,
            "wait_seconds": FIXED_WAIT_SECONDS,
            "endpoint_url": case["endpoint_url"],
            "http_ok": http_outcome["ok"],
            "http_status_code": http_outcome["status_code"],
            "http_response_snippet": http_outcome["response_snippet"],
            "http_elapsed_seconds": http_outcome["elapsed_seconds"],
            "result": "passed" if passed else "failed",
            "message": message,
        }

        report["results"].append(result)
        if passed:
            report["summary"]["passed"] += 1
        else:
            report["summary"]["failed"] += 1

    report["summary"]["total"] = len(report["results"])

    json_path, txt_path = write_reports(script_dir, report)
    print(f"JSON report: {json_path}")
    print(f"Text report: {txt_path}")

    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
