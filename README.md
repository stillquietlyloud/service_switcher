# service_switcher

A small Linux service switcher for systemd-based hosts.

## What it does

- listens for plain text commands on a TCP port (default `0.0.0.0:20100`)
- accepts `start <name>`
- looks up `<name>` in `services.json`
- starts the mapped systemd service with `systemctl start`
- exposes a second TCP port for basic health/status (default `0.0.0.0:30100`)

The status port returns JSON with:

- `healthy`
- `last_activated`

## Configuration

Edit `services.json`:

```json
{
  "command_listen_address": "0.0.0.0:20100",
  "status_listen_address": "0.0.0.0:30100",
  "services": {
    "service01": "/etc/systemd/system/service01.service"
  }
}
```

`services` maps the exposed command name to the systemd unit file path. The
service switcher starts the corresponding unit name derived from that path.

## Build

```bash
go build .
```

## Install

```bash
sudo bash install.sh
```

This builds the binary, installs it under `/opt/service_switcher`, copies the
default `services.json`, installs `service-switcher.service`, and enables it at
boot.

## Run

```bash
./service_switcher -config /path/to/services.json
```

If `-config` is not provided, the binary reads `./services.json`.

## Example commands

Start a configured service (note the **newline** after the command):

```bash
# Using echo (recommended - automatically adds newline)
echo "start service01" | nc 127.0.0.1 20100

# Or using printf with explicit newline
printf 'start service01\n' | nc 127.0.0.1 20100
```

**Important:** Commands MUST end with a newline (`\n`). Without it, the connection will hang until timeout.

Read status:

```bash
nc 127.0.0.1 30100
```

## systemd unit

An example service file is included at `service-switcher.service`.
For the standard installation path, use `sudo bash install.sh`.

## Troubleshooting

### "nc" command hangs waiting for response
- **Cause:** Command was sent without a newline character
- **Solution:** Always use `echo "start service01"` or `printf 'start service01\n'`

### Getting "error" response
- Check if the service name exists in `services.json`
- Verify the systemd unit file exists: `ls /etc/systemd/system/<service-name>.service`
- Check service-switcher logs: `journalctl -u service-switcher` or check stdout

### Updating services.json
After editing `services.json`, restart the service-switcher:
```bash
sudo systemctl restart service-switcher
```

## Portable LAN Tester (Python)

A simple portable tester script is included at `lan_service_tester.py`.

What it does:
- reads `command_listen_address` and `status_listen_address` from `services.json`
- sends `start <service>\n` to the switcher command port for each configured service
- waits a fixed `90` seconds
- sends HTTP `POST` to each service endpoint defined in the script constants
- saves `report_<timestamp>.json` and `report_<timestamp>.txt` next to the script

Important:
- endpoint URLs and payloads are intentionally hardcoded in `SERVICE_TESTS` inside `lan_service_tester.py`
- no host-level commands are used (`systemctl` is not called)

Run:
```bash
python3 lan_service_tester.py --config ./services.json
```

Exit code:
- `0` if all services pass
- `1` if one or more services fail
- `2` for config/argument errors
