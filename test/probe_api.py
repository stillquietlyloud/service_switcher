#!/usr/bin/env python3
"""Quick probe: show paths and request schemas for the currently-running service."""
import json
import sys
from urllib import request as urllib_request

BASE = "http://192.168.8.5:30000"

try:
    with urllib_request.urlopen(f"{BASE}/openapi.json", timeout=10) as r:
        d = json.loads(r.read())
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

print(f"title: {d['info']['title']}")
print(f"description: {d['info'].get('description','')}")
print("\n=== PATHS ===")
for path, methods in d["paths"].items():
    for method, spec in methods.items():
        ref = (
            spec.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref", "")
        )
        print(f"  {method.upper()} {path}  <- {ref.split('/')[-1] if ref else 'no-body'}")

print("\n=== REQUEST SCHEMAS ===")
for k, v in d.get("components", {}).get("schemas", {}).items():
    if "Request" in k:
        props = v.get("properties", {})
        required = v.get("required", [])
        print(f"  {k}:")
        for field, fdef in props.items():
            ftype = fdef.get("type", fdef.get("anyOf", [{}])[0].get("type", "?"))
            default = fdef.get("default", "REQUIRED" if field in required else "optional")
            print(f"    {field}: {ftype} = {default}")
