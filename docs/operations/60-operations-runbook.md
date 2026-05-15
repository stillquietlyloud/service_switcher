# Operations Runbook

**Audience:** Ops, sysadmin  
**Last updated:** 2026-05-15

---

## 1. Quick reference

| Task | Command |
|---|---|
| Check switcher status | `sudo systemctl status service-switcher` |
| View switcher logs | `sudo journalctl -u service-switcher -n 50` |
| Start a service | `echo "start image-sdxl" \| nc 192.168.8.5 20100` |
| Read switcher status | `nc 192.168.8.5 30100` |
| Check service health | `curl -s http://192.168.8.5:30000/health` |
| Restart switcher | `sudo systemctl restart service-switcher` |
| Check service-stopper | `sudo systemctl status service-stopper.service` |

---

## 2. Installation

### Prerequisites

- Linux with systemd
- Go compiler (`go build` must be available)
- `systemctl` with permission to start system units (root required)

### Install from source

```bash
cd /git/service_switcher
sudo bash install.sh
```

This builds the binary, copies it to `/opt/service_switcher/service_switcher`, installs `services.json`, registers and starts `service-switcher.service`.

### Verify installation

```bash
sudo systemctl status service-switcher
nc 192.168.8.5 30100
```

Expected output from status port:

```json
{"healthy":true,"last_activated":"","active_task":false, ...}
```

---

## 3. Starting a service

### Basic switch

```bash
echo "start image-sdxl" | nc 192.168.8.5 20100
```

Expected reply: `ok`

### Wait for the service to be ready

```bash
until curl -sf --max-time 5 http://192.168.8.5:30000/health > /dev/null 2>&1; do
    echo -n "."
    sleep 3
done
echo " ready"
```

### Check which service is currently active

```bash
nc 192.168.8.5 30100 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['last_activated'])"
```

### Full switch-and-wait one-liner

```bash
echo "start llm-nemotron-nano" | nc 192.168.8.5 20100 && \
until curl -sf --max-time 5 http://192.168.8.5:30000/health > /dev/null; do sleep 3; done && \
echo "ready"
```

---

## 4. Switching rules (cross-lane)

Different service types require different handling when switching.

| From | To | Method |
|---|---|---|
| Any NVIDIA (image/TTS/video) | Same NVIDIA lane | Direct — `Conflicts=` stops the old service |
| Any translator | Anything | Direct — translator `Conflicts=` covers all services |
| Anything | Any translator | Direct — same |
| NVIDIA service | LLM | **Requires service-stopper** (see below) |
| LLM | NVIDIA service | **Requires service-stopper** (see below) |
| LLM | Another LLM | Direct — LLM `Conflicts=` covers other LLMs |

### Using service-stopper for cross-lane switches

```bash
# Check service-stopper is running
sudo systemctl status service-stopper.service

# If not running, start it
sudo systemctl start service-stopper.service

# Now perform the cross-lane switch
echo "start llm-nemotron-nano" | nc 192.168.8.5 20100
```

### Alternative: use a translator as a bridge

If service-stopper is not available, a translator service stops all NVIDIA services:

```bash
# Stop NVIDIA service via translator (translator Conflicts= stops everything)
echo "start translator-accurate" | nc 192.168.8.5 20100
until curl -sf http://192.168.8.5:30000/health > /dev/null; do sleep 3; done

# Now switch to LLM (translator Conflicts= is reciprocal)
echo "start llm-nemotron-nano" | nc 192.168.8.5 20100
```

---

## 5. Config management

### Edit service list

```bash
sudo nano /opt/service_switcher/services.json
sudo systemctl restart service-switcher
```

### Config file location

- Live config: `/opt/service_switcher/services.json`
- Source: `/git/service_switcher/services.json`

### Add a new service

1. Deploy the systemd unit file to `/etc/systemd/system/<new-service>.service`.
2. Run `sudo systemctl daemon-reload`.
3. Add an entry to `services.json`:
   ```json
   "new-service": "/etc/systemd/system/new-service.service"
   ```
4. Restart the switcher: `sudo systemctl restart service-switcher`.

---

## 6. TTS voice file deployment

All TTS services return `404` until speaker reference audio is installed.

```bash
# Check if voices are available (while a TTS service is active)
curl -s http://192.168.8.5:30000/voices

# Expected when voices are missing: [] or 404
# Expected when ready: ["speaker-name", ...]
```

Voice file location: **Not verified** from repository — check each TTS service unit file for the configured voice directory path.

---

## 7. Logs and diagnostics

### Switcher logs

```bash
sudo journalctl -u service-switcher -f          # live tail
sudo journalctl -u service-switcher -n 100      # last 100 lines
sudo journalctl -u service-switcher --since "10 minutes ago"
```

### Individual service logs

```bash
sudo journalctl -u image-sdxl -n 50
sudo journalctl -u llm-nemotron-nano -n 50
```

### Check which service is bound on port 30000

```bash
sudo ss -tlnp sport = :30000
```

### Probe the active service's OpenAPI schema

```bash
curl -s http://192.168.8.5:30000/openapi.json | python3 -m json.tool | head -60
```

Or use the included probe script:

```bash
python3 /git/service_switcher/test/probe_api.py
```

---

## 8. Troubleshooting

### `nc` hangs, no response

**Cause:** Command sent without trailing newline.  
**Fix:** Always use `echo "start <name>"` (adds `\n` automatically) or `printf 'start <name>\n'`.

### Reply is `error`

1. Verify the service name is in `services.json`:
   ```bash
   python3 -c "import json; c=json.load(open('/opt/service_switcher/services.json')); print(list(c['services'].keys()))"
   ```
2. Verify the unit file exists:
   ```bash
   ls /etc/systemd/system/<service-name>.service
   ```
3. Check switcher logs:
   ```bash
   sudo journalctl -u service-switcher -n 20
   ```

### Reply is `busy`

A switch is in progress. Wait and try again. The switch will be queued automatically.

```bash
# Check if still busy
nc 192.168.8.5 30100 | python3 -c "import sys,json; d=json.load(sys.stdin); print('active:', d['active_task'], '/ pending:', d['pending_switch'])"
```

### Service never becomes healthy (health check always fails)

1. Check the service actually started:
   ```bash
   sudo systemctl status <service-name>
   sudo journalctl -u <service-name> -n 30
   ```
2. Check port 30000 is bound:
   ```bash
   sudo ss -tlnp sport = :30000
   ```
3. Check for cross-lane conflict (NVIDIA service still running after LLM switch request):
   ```bash
   sudo systemctl status service-stopper.service
   sudo systemctl start service-stopper.service
   ```

### TTS returns `404 Voice not found`

Install voice reference audio files for the active TTS service. See Section 6.

---

## 9. Running the workload test

Full end-to-end quality test of all services:

```bash
# All services
python3 /git/service_switcher/test/lan_workload_test.py

# Specific group
python3 /git/service_switcher/test/lan_workload_test.py --groups nvidia

# Specific service
python3 /git/service_switcher/test/lan_workload_test.py --services image-sdxl
```

Reports are written to `test/workload_report_<timestamp>.json` and `.txt`.

---

## 10. Switcher process management

```bash
# Status
sudo systemctl status service-switcher

# Start / stop / restart
sudo systemctl start service-switcher
sudo systemctl stop service-switcher
sudo systemctl restart service-switcher

# Enable / disable at boot
sudo systemctl enable service-switcher
sudo systemctl disable service-switcher
```

Binary location: `/opt/service_switcher/service_switcher`  
Config location: `/opt/service_switcher/services.json`  
Unit file: `/etc/systemd/system/service-switcher.service`

---

## Evidence

- [install.sh](../../install.sh)
- [service-switcher.service](../../service-switcher.service)
- [services.json](../../services.json)
- [test/LAN_WORKLOAD_TEST.md](../../test/LAN_WORKLOAD_TEST.md) — Sections 2 and 12
