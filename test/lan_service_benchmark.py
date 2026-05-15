#!/usr/bin/env python3
"""LAN benchmark harness for service_switcher.

This script runs from another host on the LAN and measures:
- Wake-on-LAN boot readiness time (optional)
- Switch command acknowledgement time
- Warm-up time to first ready endpoint response
- Production latency (p50/p95/p99) after warm-up
- Switching/shutdown delay for previous service after a switch

Execution order is group-based and defaults to AMD first, then NVIDIA.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import socket
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib import error, request
from urllib.parse import urlparse

DEFAULT_SOCKET_TIMEOUT_SECONDS = 10.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 120.0
DEFAULT_READINESS_TIMEOUT_SECONDS = 900.0
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 300.0
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_PRODUCTION_REQUESTS = 20
DEFAULT_PRODUCTION_INTERVAL_SECONDS = 1.0
MAX_RESPONSE_SNIPPET = 1200
DEFAULT_MAX_RESPONSE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_LINK_DOWNLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_GROUP_ORDER = ["amd", "nvidia"]
TEXTUAL_CONTENT_TYPES = (
    "application/json",
    "text/plain",
    "text/html",
    "text/markdown",
    "application/xml",
    "text/xml",
)
MEDIA_CONTENT_TYPE_PREFIXES = ("image/", "audio/", "video/")


@dataclass(frozen=True)
class SampleOptions:
    max_response_bytes: int
    max_link_download_bytes: int
    download_linked_assets: bool
    save_all_production_samples: bool
    save_response_bodies: bool


@dataclass(frozen=True)
class ServiceCase:
    service_name: str
    group: str
    endpoint_url: str
    method: str
    payload: Dict[str, Any]
    expected_status_codes: List[int]
    response_must_contain: str


@dataclass(frozen=True)
class Timeouts:
    socket_seconds: float
    http_seconds: float
    readiness_seconds: float
    shutdown_seconds: float


def slugify(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    return compact.strip("-.") or "sample"


def extension_for_content_type(content_type: str, fallback_text: bool) -> str:
    text = content_type.lower()
    if "json" in text:
        return ".json"
    if text.startswith("text/"):
        return ".txt"
    if text.startswith("image/"):
        subtype = text.split("/", 1)[1].split(";", 1)[0].strip()
        if subtype in {"jpeg", "jpg"}:
            return ".jpg"
        return f".{subtype}" if subtype else ".img"
    if text.startswith("audio/"):
        subtype = text.split("/", 1)[1].split(";", 1)[0].strip()
        return f".{subtype}" if subtype else ".audio"
    if text.startswith("video/"):
        subtype = text.split("/", 1)[1].split(";", 1)[0].strip()
        return f".{subtype}" if subtype else ".video"
    return ".txt" if fallback_text else ".bin"


def is_utf8_text(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def save_artifact_file(
    script_dir: Path,
    service_name: str,
    phase: str,
    index: int,
    suffix: str,
    extension: str,
    payload: bytes,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    safe_service = slugify(service_name)
    safe_phase = slugify(phase)
    safe_suffix = slugify(suffix)
    filename = f"sample_{stamp}_{safe_service}_{safe_phase}_{index:03d}_{safe_suffix}{extension}"
    path = script_dir / filename
    path.write_bytes(payload)
    return path


def deep_collect_strings(value: Any) -> List[str]:
    strings: List[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, list):
        for item in value:
            strings.extend(deep_collect_strings(item))
    elif isinstance(value, dict):
        for nested in value.values():
            strings.extend(deep_collect_strings(nested))
    return strings


def extract_data_uri_payload(text: str) -> Optional[Tuple[str, bytes]]:
    if not text.startswith("data:") or ";base64," not in text:
        return None
    prefix, payload = text.split(",", 1)
    meta = prefix[5:]
    mime = meta.split(";", 1)[0] if meta else "application/octet-stream"
    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception:  # noqa: BLE001
        return None
    return mime, decoded


def download_asset_url(url: str, timeout_seconds: float, max_bytes: int) -> Tuple[Optional[bytes], str, str]:
    req = request.Request(url=url, method="GET", headers={"Accept": "*/*"})
    with request.urlopen(req, timeout=timeout_seconds) as resp:
        content_type = str(resp.headers.get("Content-Type", "application/octet-stream"))
        final_url = str(getattr(resp, "url", url))
        data = resp.read(max_bytes)
    return data, content_type, final_url


def write_response_samples(
    *,
    script_dir: Path,
    service_name: str,
    phase: str,
    response: Dict[str, Any],
    sample_options: SampleOptions,
    timeouts: Timeouts,
) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    if not sample_options.save_response_bodies:
        return artifacts

    payload: bytes = response.get("response_bytes", b"")
    content_type = str(response.get("content_type", "application/octet-stream"))
    if payload:
        textish = content_type.startswith(TEXTUAL_CONTENT_TYPES) or is_utf8_text(payload)
        ext = extension_for_content_type(content_type, textish)
        artifact_path = save_artifact_file(
            script_dir=script_dir,
            service_name=service_name,
            phase=phase,
            index=1,
            suffix="response",
            extension=ext,
            payload=payload,
        )
        artifacts.append(
            {
                "type": "response_body",
                "content_type": content_type,
                "path": str(artifact_path),
                "size_bytes": len(payload),
            }
        )

    extracted_count = 0
    parsed_json: Optional[Any] = None
    if payload:
        decoded = payload.decode("utf-8", errors="replace")
        if "json" in content_type.lower() or decoded.strip().startswith(("{", "[")):
            try:
                parsed_json = json.loads(decoded)
            except json.JSONDecodeError:
                parsed_json = None

    candidate_strings: List[str] = []
    if parsed_json is not None:
        candidate_strings = deep_collect_strings(parsed_json)

    if not candidate_strings and payload and is_utf8_text(payload):
        candidate_strings = [payload.decode("utf-8", errors="replace")]

    for candidate in candidate_strings:
        data_uri = extract_data_uri_payload(candidate)
        if data_uri is not None:
            mime, data = data_uri
            extracted_count += 1
            ext = extension_for_content_type(mime, fallback_text=False)
            artifact_path = save_artifact_file(
                script_dir=script_dir,
                service_name=service_name,
                phase=phase,
                index=100 + extracted_count,
                suffix="embedded",
                extension=ext,
                payload=data,
            )
            artifacts.append(
                {
                    "type": "embedded_data_uri",
                    "content_type": mime,
                    "path": str(artifact_path),
                    "size_bytes": len(data),
                }
            )
            continue

        if sample_options.download_linked_assets and candidate.startswith(("http://", "https://")):
            try:
                data, linked_type, final_url = download_asset_url(
                    url=candidate,
                    timeout_seconds=timeouts.http_seconds,
                    max_bytes=sample_options.max_link_download_bytes,
                )
                if data:
                    extracted_count += 1
                    ext = extension_for_content_type(linked_type, fallback_text=is_utf8_text(data))
                    parsed = urlparse(final_url)
                    tail = Path(parsed.path).name or "linked"
                    artifact_path = save_artifact_file(
                        script_dir=script_dir,
                        service_name=service_name,
                        phase=phase,
                        index=200 + extracted_count,
                        suffix=f"linked-{tail}",
                        extension=ext,
                        payload=data,
                    )
                    artifacts.append(
                        {
                            "type": "linked_asset",
                            "source_url": final_url,
                            "content_type": linked_type,
                            "path": str(artifact_path),
                            "size_bytes": len(data),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                artifacts.append(
                    {
                        "type": "linked_asset_error",
                        "source_url": candidate,
                        "error": str(exc),
                    }
                )

    return artifacts


def compact_http_response(response: Dict[str, Any]) -> Dict[str, Any]:
    payload = response.get("response_bytes", b"")
    byte_len = len(payload) if isinstance(payload, (bytes, bytearray)) else 0
    return {
        "transport_ok": bool(response.get("transport_ok", False)),
        "status_code": response.get("status_code"),
        "response_snippet": str(response.get("response_snippet", ""))[:MAX_RESPONSE_SNIPPET],
        "elapsed_seconds": response.get("elapsed_seconds"),
        "content_type": response.get("content_type"),
        "final_url": response.get("final_url"),
        "response_bytes_len": byte_len,
    }


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


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_switcher_config(path: Path) -> Dict[str, Any]:
    raw = load_json(path)
    command_address = raw.get("command_listen_address", "").strip()
    status_address = raw.get("status_listen_address", "").strip()
    services = raw.get("services", {})

    if not command_address or not status_address:
        raise ValueError("services config must include command_listen_address and status_listen_address")
    if not isinstance(services, dict) or not services:
        raise ValueError("services config must include at least one service")

    return raw


def load_cases(benchmark_config: Dict[str, Any]) -> Dict[str, ServiceCase]:
    tests = benchmark_config.get("service_tests", [])
    if not isinstance(tests, list) or not tests:
        raise ValueError("benchmark config must include non-empty service_tests")

    parsed: Dict[str, ServiceCase] = {}
    for item in tests:
        if not isinstance(item, dict):
            raise ValueError("each service_tests entry must be an object")

        service_name = str(item.get("service_name", "")).strip()
        group = str(item.get("group", "")).strip().lower()
        endpoint_url = str(item.get("endpoint_url", "")).strip()
        method = str(item.get("method", "POST")).strip().upper()
        payload = item.get("payload", {})
        expected_codes = item.get("expected_status_codes", [200])
        response_must_contain = str(item.get("response_must_contain", ""))

        if not service_name or not group or not endpoint_url:
            raise ValueError("service_tests entries must include service_name, group, endpoint_url")
        if method not in {"POST", "GET"}:
            raise ValueError(f"unsupported method {method} for {service_name}")
        if method == "POST" and not isinstance(payload, dict):
            raise ValueError(f"payload for {service_name} must be an object for POST")
        if not isinstance(expected_codes, list) or not expected_codes:
            raise ValueError(f"expected_status_codes for {service_name} must be a non-empty list")

        try:
            codes = [int(code) for code in expected_codes]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid expected_status_codes for {service_name}") from exc

        if service_name in parsed:
            raise ValueError(f"duplicate service case: {service_name}")

        parsed[service_name] = ServiceCase(
            service_name=service_name,
            group=group,
            endpoint_url=endpoint_url,
            method=method,
            payload=payload,
            expected_status_codes=codes,
            response_must_contain=response_must_contain,
        )

    return parsed


def order_services(
    switcher_services: Sequence[str],
    cases: Dict[str, ServiceCase],
    group_order: Sequence[str],
    selected_groups: Optional[Sequence[str]],
) -> List[str]:
    configured = set(switcher_services)
    case_names = set(cases.keys())

    missing_case = sorted(configured - case_names)
    if missing_case:
        raise ValueError(f"missing service_tests entries for: {', '.join(missing_case)}")

    missing_from_switcher = sorted(case_names - configured)
    if missing_from_switcher:
        raise ValueError(
            "service_tests contains names not present in services config: "
            + ", ".join(missing_from_switcher)
        )

    groups = [group.lower() for group in (selected_groups or group_order)]
    known_groups = {case.group for case in cases.values()}
    unknown_groups = [group for group in groups if group not in known_groups]
    if unknown_groups:
        raise ValueError(f"requested groups not present in service_tests: {', '.join(unknown_groups)}")

    ordered: List[str] = []
    for group in groups:
        group_members = sorted([name for name in switcher_services if cases[name].group == group])
        ordered.extend(group_members)

    if not ordered:
        raise ValueError("no services selected after applying group filters")

    return ordered


def send_magic_packet(mac_address: str, broadcast_ip: str, port: int) -> None:
    cleaned = mac_address.replace("-", "").replace(":", "").strip()
    if len(cleaned) != 12:
        raise ValueError(f"invalid MAC address: {mac_address}")

    try:
        mac_bytes = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid MAC address: {mac_address}") from exc

    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, port))


def tcp_port_open(host: str, port: int, timeout_seconds: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def send_switch_command(host: str, port: int, service_name: str, timeout_seconds: float) -> Dict[str, Any]:
    command = f"start {service_name}\n".encode("utf-8")
    started_at = time.perf_counter()

    with socket.create_connection((host, port), timeout=timeout_seconds) as conn:
        conn.sendall(command)
        conn.settimeout(timeout_seconds)
        data = conn.recv(256)

    elapsed = time.perf_counter() - started_at
    response = data.decode("utf-8", errors="replace").strip()
    return {
        "ok": response == "ok",
        "response": response,
        "elapsed_seconds": round(elapsed, 3),
    }


def read_switcher_status(host: str, port: int, timeout_seconds: float) -> Dict[str, Any]:
    with socket.create_connection((host, port), timeout=timeout_seconds) as conn:
        conn.settimeout(timeout_seconds)
        data = conn.recv(4096)

    text = data.decode("utf-8", errors="replace").strip()
    parsed: Dict[str, Any] = json.loads(text) if text else {}
    return parsed


def http_request(
    url: str,
    method: str,
    payload: Dict[str, Any],
    timeout_seconds: float,
    max_bytes: int,
) -> Dict[str, Any]:
    body: Optional[bytes] = None
    headers = {"Accept": "application/json, text/plain, */*"}

    if method == "POST":
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url=url, data=body, method=method, headers=headers)

    started_at = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            resp_body = resp.read(max_bytes)
            status_code = getattr(resp, "status", 200)
            snippet = resp_body.decode("utf-8", errors="replace")
            ok_transport = True
            content_type = str(resp.headers.get("Content-Type", "application/octet-stream"))
            final_url = str(getattr(resp, "url", url))
    except error.HTTPError as exc:
        body_bytes = exc.read(max_bytes)
        status_code = exc.code
        snippet = body_bytes.decode("utf-8", errors="replace")
        ok_transport = True
        resp_body = body_bytes
        content_type = str(exc.headers.get("Content-Type", "application/octet-stream")) if exc.headers else "application/octet-stream"
        final_url = str(getattr(exc, "url", url))
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started_at
        return {
            "transport_ok": False,
            "status_code": None,
            "response_snippet": str(exc),
            "elapsed_seconds": round(elapsed, 3),
            "response_bytes": b"",
            "content_type": "application/octet-stream",
            "final_url": url,
        }

    elapsed = time.perf_counter() - started_at
    return {
        "transport_ok": ok_transport,
        "status_code": status_code,
        "response_snippet": snippet[:MAX_RESPONSE_SNIPPET],
        "elapsed_seconds": round(elapsed, 3),
        "response_bytes": resp_body,
        "content_type": content_type,
        "final_url": final_url,
    }


def is_ready(case: ServiceCase, response: Dict[str, Any]) -> bool:
    if not response.get("transport_ok", False):
        return False

    status_code = response.get("status_code")
    if status_code not in case.expected_status_codes:
        return False

    required = case.response_must_contain
    if required and required not in str(response.get("response_snippet", "")):
        return False

    return True


def quantile_nearest_rank(values: List[float], q: float) -> float:
    if not values:
        return math.nan
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)

    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def run_production_benchmark(
    case: ServiceCase,
    timeouts: Timeouts,
    sample_options: SampleOptions,
    script_dir: Path,
    requests_count: int,
    interval_seconds: float,
) -> Dict[str, Any]:
    latencies: List[float] = []
    successes = 0
    failures = 0
    last_error = ""
    request_artifacts: List[Dict[str, Any]] = []

    for index in range(requests_count):
        response = http_request(
            url=case.endpoint_url,
            method=case.method,
            payload=case.payload,
            timeout_seconds=timeouts.http_seconds,
            max_bytes=sample_options.max_response_bytes,
        )

        if sample_options.save_all_production_samples:
            artifacts = write_response_samples(
                script_dir=script_dir,
                service_name=case.service_name,
                phase=f"production-{index + 1:03d}",
                response=response,
                sample_options=sample_options,
                timeouts=timeouts,
            )
            request_artifacts.append({"request_index": index + 1, "artifacts": artifacts})

        latency = float(response["elapsed_seconds"])
        latencies.append(latency)
        ready = is_ready(case, response)
        if ready:
            successes += 1
        else:
            failures += 1
            last_error = str(response.get("response_snippet", ""))

        if index + 1 < requests_count:
            time.sleep(interval_seconds)

    p50 = quantile_nearest_rank(latencies, 0.50)
    p95 = quantile_nearest_rank(latencies, 0.95)
    p99 = quantile_nearest_rank(latencies, 0.99)

    return {
        "requests": requests_count,
        "successes": successes,
        "failures": failures,
        "success_rate": round(successes / requests_count, 3) if requests_count > 0 else 0.0,
        "latency_seconds": {
            "min": round(min(latencies), 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
            "avg": round(statistics.fmean(latencies), 3) if latencies else None,
            "p50": round(p50, 3) if not math.isnan(p50) else None,
            "p95": round(p95, 3) if not math.isnan(p95) else None,
            "p99": round(p99, 3) if not math.isnan(p99) else None,
        },
        "last_error_snippet": last_error,
        "request_artifacts": request_artifacts,
    }


def monitor_transition(
    previous_case: Optional[ServiceCase],
    current_case: ServiceCase,
    switch_started_perf: float,
    timeouts: Timeouts,
    sample_options: SampleOptions,
    script_dir: Path,
    poll_interval_seconds: float,
) -> Dict[str, Any]:
    started = time.perf_counter()
    ready_elapsed: Optional[float] = None
    shutdown_elapsed: Optional[float] = None
    ready_probe: Dict[str, Any] = {"transport_ok": False, "status_code": None, "response_snippet": ""}
    prev_probe: Dict[str, Any] = {"transport_ok": False, "status_code": None, "response_snippet": ""}
    overlap_seen = False

    while True:
        now = time.perf_counter()
        total_elapsed = now - started

        if ready_elapsed is None:
            ready_probe = http_request(
                url=current_case.endpoint_url,
                method=current_case.method,
                payload=current_case.payload,
                timeout_seconds=timeouts.http_seconds,
                max_bytes=sample_options.max_response_bytes,
            )
            if is_ready(current_case, ready_probe):
                ready_elapsed = time.perf_counter() - switch_started_perf

        if previous_case is not None and shutdown_elapsed is None:
            prev_probe = http_request(
                url=previous_case.endpoint_url,
                method=previous_case.method,
                payload=previous_case.payload,
                timeout_seconds=timeouts.http_seconds,
                max_bytes=sample_options.max_response_bytes,
            )
            prev_still_ready = is_ready(previous_case, prev_probe)
            current_ready = ready_elapsed is not None
            if prev_still_ready and current_ready:
                overlap_seen = True
            if not prev_still_ready:
                shutdown_elapsed = time.perf_counter() - switch_started_perf

        current_done = ready_elapsed is not None
        previous_done = previous_case is None or shutdown_elapsed is not None

        timed_out_ready = (time.perf_counter() - switch_started_perf) >= timeouts.readiness_seconds
        timed_out_shutdown = (time.perf_counter() - switch_started_perf) >= timeouts.shutdown_seconds

        if current_done and previous_done:
            break

        if timed_out_ready and (previous_done or timed_out_shutdown):
            break

        if timed_out_shutdown and previous_case is not None and current_done:
            break

        if total_elapsed > max(timeouts.readiness_seconds, timeouts.shutdown_seconds) + timeouts.http_seconds:
            break

        time.sleep(poll_interval_seconds)

    ready_artifacts = write_response_samples(
        script_dir=script_dir,
        service_name=current_case.service_name,
        phase="warmup",
        response=ready_probe,
        sample_options=sample_options,
        timeouts=timeouts,
    )

    previous_artifacts: List[Dict[str, Any]] = []
    if previous_case is not None:
        previous_artifacts = write_response_samples(
            script_dir=script_dir,
            service_name=previous_case.service_name,
            phase=f"shutdown-after-switch-to-{current_case.service_name}",
            response=prev_probe,
            sample_options=sample_options,
            timeouts=timeouts,
        )

    return {
        "warmup_seconds": round(ready_elapsed, 3) if ready_elapsed is not None else None,
        "shutdown_delay_seconds": round(shutdown_elapsed, 3) if shutdown_elapsed is not None else None,
        "current_ready_probe": ready_probe,
        "previous_probe": prev_probe,
        "current_ready_artifacts": ready_artifacts,
        "previous_probe_artifacts": previous_artifacts,
        "overlap_seen": overlap_seen,
    }


def wait_for_switcher_after_wol(
    command_host: str,
    command_port: int,
    status_host: str,
    status_port: int,
    timeout_seconds: float,
    poll_interval_seconds: float,
    socket_timeout_seconds: float,
) -> Dict[str, Any]:
    start_perf = time.perf_counter()

    cmd_ready_at: Optional[float] = None
    status_ready_at: Optional[float] = None
    status_last: Dict[str, Any] = {}

    while True:
        elapsed = time.perf_counter() - start_perf
        if cmd_ready_at is None:
            if tcp_port_open(command_host, command_port, socket_timeout_seconds):
                cmd_ready_at = elapsed

        if status_ready_at is None:
            try:
                status_last = read_switcher_status(status_host, status_port, socket_timeout_seconds)
                if bool(status_last.get("healthy", False)):
                    status_ready_at = elapsed
            except Exception:  # noqa: BLE001
                pass

        if cmd_ready_at is not None and status_ready_at is not None:
            break

        if elapsed >= timeout_seconds:
            break

        time.sleep(poll_interval_seconds)

    return {
        "command_port_ready_seconds": round(cmd_ready_at, 3) if cmd_ready_at is not None else None,
        "status_healthy_seconds": round(status_ready_at, 3) if status_ready_at is not None else None,
        "last_status": status_last,
        "timed_out": cmd_ready_at is None or status_ready_at is None,
    }


def endpoint_port_summary(cases: Dict[str, ServiceCase]) -> Dict[str, Any]:
    by_port: Dict[str, List[str]] = {}
    parse_errors: List[str] = []
    for service_name, case in sorted(cases.items()):
        try:
            parsed = urlparse(case.endpoint_url)
            if not parsed.scheme or not parsed.hostname or parsed.port is None:
                raise ValueError("missing hostname or port")
            key = f"{parsed.hostname}:{parsed.port}"
            by_port.setdefault(key, []).append(service_name)
        except Exception as exc:  # noqa: BLE001
            parse_errors.append(f"{service_name}: {exc}")

    return {
        "port_groups": [{"endpoint": key, "services": names} for key, names in sorted(by_port.items())],
        "parse_errors": parse_errors,
    }


def build_call_examples(
    *,
    command_host: str,
    command_port: int,
    cases: Dict[str, ServiceCase],
) -> Dict[str, Dict[str, str]]:
    examples: Dict[str, Dict[str, str]] = {}
    for service_name, case in sorted(cases.items()):
        switch_cmd = f"echo 'start {service_name}' | nc {command_host} {command_port}"
        if case.method == "POST":
            payload = json.dumps(case.payload)
            endpoint_cmd = (
                "curl -sS -X POST "
                f"-H 'Content-Type: application/json' --data '{payload}' '{case.endpoint_url}'"
            )
        else:
            endpoint_cmd = f"curl -sS -X GET '{case.endpoint_url}'"

        examples[service_name] = {
            "switch_command": switch_cmd,
            "endpoint_command": endpoint_cmd,
        }

    return examples


def write_reports(script_dir: Path, report: Dict[str, Any]) -> Tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    json_path = script_dir / f"benchmark_report_{stamp}.json"
    txt_path = script_dir / f"benchmark_report_{stamp}.txt"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append(f"timestamp_utc: {report['timestamp_utc']}")
    lines.append(f"benchmark_config_path: {report['benchmark_config_path']}")
    lines.append(f"services_config_path: {report['services_config_path']}")
    lines.append(f"command_address: {report['command_address']}")
    lines.append(f"status_address: {report['status_address']}")
    lines.append(f"group_order: {', '.join(report['group_order'])}")
    lines.append("")

    port_review = report.get("port_review", {})
    if port_review:
        lines.append("port_review:")
        for group in port_review.get("port_groups", []):
            services_line = ", ".join(group.get("services", []))
            lines.append(f"  {group.get('endpoint')}: {services_line}")
        for parse_error in port_review.get("parse_errors", []):
            lines.append(f"  parse_error: {parse_error}")
        lines.append("")

    wol = report.get("wol", {})
    if wol:
        lines.append("wol:")
        lines.append(f"  enabled={wol.get('enabled', False)}")
        lines.append(f"  command_port_ready_seconds={wol.get('command_port_ready_seconds')}")
        lines.append(f"  status_healthy_seconds={wol.get('status_healthy_seconds')}")
        lines.append(f"  timed_out={wol.get('timed_out')}")
        lines.append("")

    summary = report["summary"]
    lines.append(
        "summary: "
        f"total={summary['total']} passed={summary['passed']} failed={summary['failed']} "
        f"avg_warmup={summary['avg_warmup_seconds']}s avg_switch={summary['avg_switch_seconds']}s"
    )
    lines.append("")

    for result in report["results"]:
        lines.append(f"service: {result['service_name']} group={result['group']}")
        lines.append(
            f"switch_ok={result['switch_ok']} switch_elapsed={result['switch_elapsed_seconds']}s "
            f"response={result['switch_response']}"
        )
        lines.append(
            f"warmup_seconds={result['warmup_seconds']} shutdown_delay_seconds={result['shutdown_delay_seconds']} "
            f"overlap_seen={result['overlap_seen']}"
        )
        lines.append(
            "samples: "
            f"warmup={len(result.get('warmup_artifacts', []))} "
            f"shutdown={len(result.get('shutdown_probe_artifacts', []))} "
            f"production={result['production'].get('saved_artifact_count', 0)}"
        )
        prod = result["production"]
        lat = prod["latency_seconds"]
        lines.append(
            "production: "
            f"req={prod['requests']} success={prod['successes']} fail={prod['failures']} "
            f"p50={lat['p50']}s p95={lat['p95']}s p99={lat['p99']}s"
        )
        lines.append(f"result={result['result']} message={result['message']}")
        call_examples = result.get("call_examples", {})
        if call_examples:
            lines.append(f"switch_call={call_examples.get('switch_command', '')}")
            lines.append(f"endpoint_call={call_examples.get('endpoint_command', '')}")
        for artifact in result.get("all_artifacts", []):
            if "path" in artifact:
                lines.append(f"artifact={artifact['path']}")
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LAN benchmark harness for service_switcher")
    parser.add_argument(
        "--benchmark-config",
        default="test/lan_benchmark_config.json",
        help="Path to benchmark configuration JSON",
    )
    parser.add_argument(
        "--services-config",
        default="services.json",
        help="Path to services.json with command/status listen addresses",
    )
    parser.add_argument(
        "--groups",
        nargs="*",
        help="Optional group override list, e.g. --groups amd nvidia",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent

    benchmark_config_path = Path(args.benchmark_config).expanduser().resolve()
    services_config_path = Path(args.services_config).expanduser().resolve()

    if not benchmark_config_path.exists():
        print(f"ERROR: benchmark config not found: {benchmark_config_path}")
        return 2
    if not services_config_path.exists():
        print(f"ERROR: services config not found: {services_config_path}")
        return 2

    try:
        benchmark_config = load_json(benchmark_config_path)
        switcher_config = load_switcher_config(services_config_path)
        command_host, command_port = parse_address(switcher_config["command_listen_address"])
        status_host, status_port = parse_address(switcher_config["status_listen_address"])
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: invalid config input: {exc}")
        return 2

    timeout_cfg = benchmark_config.get("timeouts", {})
    timeouts = Timeouts(
        socket_seconds=float(timeout_cfg.get("socket_seconds", DEFAULT_SOCKET_TIMEOUT_SECONDS)),
        http_seconds=float(timeout_cfg.get("http_seconds", DEFAULT_HTTP_TIMEOUT_SECONDS)),
        readiness_seconds=float(timeout_cfg.get("readiness_seconds", DEFAULT_READINESS_TIMEOUT_SECONDS)),
        shutdown_seconds=float(timeout_cfg.get("shutdown_seconds", DEFAULT_SHUTDOWN_TIMEOUT_SECONDS)),
    )

    poll_interval_seconds = float(benchmark_config.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS))
    production_cfg = benchmark_config.get("production", {})
    production_requests = int(production_cfg.get("requests", DEFAULT_PRODUCTION_REQUESTS))
    production_interval_seconds = float(
        production_cfg.get("interval_seconds", DEFAULT_PRODUCTION_INTERVAL_SECONDS)
    )
    samples_cfg = benchmark_config.get("samples", {})
    sample_options = SampleOptions(
        max_response_bytes=int(samples_cfg.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)),
        max_link_download_bytes=int(
            samples_cfg.get("max_link_download_bytes", DEFAULT_MAX_LINK_DOWNLOAD_BYTES)
        ),
        download_linked_assets=bool(samples_cfg.get("download_linked_assets", True)),
        save_all_production_samples=bool(samples_cfg.get("save_all_production_samples", True)),
        save_response_bodies=bool(samples_cfg.get("save_response_bodies", True)),
    )

    group_order = [
        str(group).strip().lower() for group in benchmark_config.get("group_order", DEFAULT_GROUP_ORDER)
    ]
    cases = load_cases(benchmark_config)

    configured_services = sorted(switcher_config["services"].keys())
    selected_groups = args.groups if args.groups else None
    try:
        ordered_services = order_services(
            switcher_services=configured_services,
            cases=cases,
            group_order=group_order,
            selected_groups=selected_groups,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: unable to order services: {exc}")
        return 2

    command_examples = build_call_examples(
        command_host=command_host,
        command_port=command_port,
        cases=cases,
    )

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_config_path": str(benchmark_config_path),
        "services_config_path": str(services_config_path),
        "command_address": switcher_config["command_listen_address"],
        "status_address": switcher_config["status_listen_address"],
        "group_order": selected_groups or group_order,
        "port_review": endpoint_port_summary(cases),
        "service_name_review": {
            "configured_service_count": len(configured_services),
            "case_service_count": len(cases),
            "missing_in_cases": sorted(set(configured_services) - set(cases.keys())),
            "extra_in_cases": sorted(set(cases.keys()) - set(configured_services)),
        },
        "wol": {},
        "results": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "avg_warmup_seconds": None,
            "avg_switch_seconds": None,
            "artifact_files_saved": 0,
        },
    }

    wol_cfg = benchmark_config.get("wol", {})
    wol_enabled = bool(wol_cfg.get("enabled", False))
    if wol_enabled:
        target_mac = str(wol_cfg.get("target_mac", "")).strip()
        broadcast_ip = str(wol_cfg.get("broadcast_ip", "")).strip()
        wol_port = int(wol_cfg.get("port", 9))
        wol_wait_timeout = float(wol_cfg.get("wait_timeout_seconds", 600.0))

        if not target_mac or not broadcast_ip:
            print("ERROR: wol.enabled=true requires target_mac and broadcast_ip")
            return 2

        print(f"[wol] sending magic packet to {target_mac} via {broadcast_ip}:{wol_port}")
        try:
            send_magic_packet(target_mac, broadcast_ip, wol_port)
            wol_result = wait_for_switcher_after_wol(
                command_host=command_host,
                command_port=command_port,
                status_host=status_host,
                status_port=status_port,
                timeout_seconds=wol_wait_timeout,
                poll_interval_seconds=poll_interval_seconds,
                socket_timeout_seconds=timeouts.socket_seconds,
            )
            wol_result["enabled"] = True
            report["wol"] = wol_result
        except Exception as exc:  # noqa: BLE001
            report["wol"] = {
                "enabled": True,
                "error": str(exc),
                "timed_out": True,
            }

    previous_case: Optional[ServiceCase] = None
    warmup_values: List[float] = []
    switch_values: List[float] = []

    for service_name in ordered_services:
        case = cases[service_name]

        print(f"[{service_name}] sending switch command")
        switch_started_perf = time.perf_counter()
        try:
            switch_outcome = send_switch_command(
                host=command_host,
                port=command_port,
                service_name=service_name,
                timeout_seconds=timeouts.socket_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            switch_outcome = {
                "ok": False,
                "response": f"switch_error: {exc}",
                "elapsed_seconds": 0.0,
            }

        try:
            status_snapshot = read_switcher_status(status_host, status_port, timeouts.socket_seconds)
        except Exception as exc:  # noqa: BLE001
            status_snapshot = {"status_error": str(exc)}

        transition = monitor_transition(
            previous_case=previous_case,
            current_case=case,
            switch_started_perf=switch_started_perf,
            timeouts=timeouts,
            sample_options=sample_options,
            script_dir=script_dir,
            poll_interval_seconds=poll_interval_seconds,
        )

        production: Dict[str, Any]
        if transition["warmup_seconds"] is not None:
            print(f"[{service_name}] running production benchmark ({production_requests} requests)")
            production = run_production_benchmark(
                case=case,
                timeouts=timeouts,
                sample_options=sample_options,
                script_dir=script_dir,
                requests_count=production_requests,
                interval_seconds=production_interval_seconds,
            )
        else:
            production = {
                "requests": production_requests,
                "successes": 0,
                "failures": production_requests,
                "success_rate": 0.0,
                "latency_seconds": {
                    "min": None,
                    "max": None,
                    "avg": None,
                    "p50": None,
                    "p95": None,
                    "p99": None,
                },
                "last_error_snippet": "warmup did not reach ready criteria",
                "request_artifacts": [],
            }

        production_artifacts: List[Dict[str, Any]] = []
        for item in production.get("request_artifacts", []):
            production_artifacts.extend(item.get("artifacts", []))
        production["saved_artifact_count"] = len([a for a in production_artifacts if "path" in a])

        all_artifacts: List[Dict[str, Any]] = []
        all_artifacts.extend(transition.get("current_ready_artifacts", []))
        all_artifacts.extend(transition.get("previous_probe_artifacts", []))
        all_artifacts.extend(production_artifacts)
        report["summary"]["artifact_files_saved"] += len([a for a in all_artifacts if "path" in a])

        passed = bool(
            switch_outcome["ok"]
            and transition["warmup_seconds"] is not None
            and production["success_rate"] > 0
        )
        message = "ok" if passed else "switch, warmup, or production checks failed"

        if transition["warmup_seconds"] is not None:
            warmup_values.append(float(transition["warmup_seconds"]))
        switch_values.append(float(switch_outcome["elapsed_seconds"]))

        result = {
            "service_name": service_name,
            "group": case.group,
            "switch_ok": switch_outcome["ok"],
            "switch_response": switch_outcome["response"],
            "switch_elapsed_seconds": switch_outcome["elapsed_seconds"],
            "status_snapshot": status_snapshot,
            "warmup_seconds": transition["warmup_seconds"],
            "shutdown_delay_seconds": transition["shutdown_delay_seconds"],
            "overlap_seen": transition["overlap_seen"],
            "ready_probe": compact_http_response(transition["current_ready_probe"]),
            "previous_probe": compact_http_response(transition["previous_probe"]),
            "warmup_artifacts": transition.get("current_ready_artifacts", []),
            "shutdown_probe_artifacts": transition.get("previous_probe_artifacts", []),
            "endpoint_url": case.endpoint_url,
            "call_examples": command_examples.get(service_name, {}),
            "production": production,
            "all_artifacts": all_artifacts,
            "result": "passed" if passed else "failed",
            "message": message,
        }

        report["results"].append(result)
        if passed:
            report["summary"]["passed"] += 1
        else:
            report["summary"]["failed"] += 1

        previous_case = case

    report["summary"]["total"] = len(report["results"])
    if warmup_values:
        report["summary"]["avg_warmup_seconds"] = round(statistics.fmean(warmup_values), 3)
    if switch_values:
        report["summary"]["avg_switch_seconds"] = round(statistics.fmean(switch_values), 3)

    json_path, txt_path = write_reports(script_dir, report)
    print(f"JSON report: {json_path}")
    print(f"Text report: {txt_path}")

    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
