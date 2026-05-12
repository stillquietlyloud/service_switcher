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

## Run

```bash
./service_switcher -config /path/to/services.json
```

If `-config` is not provided, the binary reads `./services.json`.

## Example commands

Start a configured service:

```bash
printf 'start service01\n' | nc 127.0.0.1 20100
```

Read status:

```bash
nc 127.0.0.1 30100
```

## systemd unit

An example service file is included at `service-switcher.service`. Copy it to
`/etc/systemd/system/service-switcher.service`, adjust paths, reload systemd,
and enable it at boot.
