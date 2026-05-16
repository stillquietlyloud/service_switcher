#!/usr/bin/env bash
set -euo pipefail

info()  { echo "[INFO]  $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Run as root: sudo bash install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR=/opt/service_switcher
UNIT_NAME=service-switcher.service
UNIT_DEST="/etc/systemd/system/$UNIT_NAME"

command -v go >/dev/null 2>&1 || error "Go is required to build service_switcher"

info "Building service_switcher …"
install -d -m 0755 "$INSTALL_DIR"
go -C "$SCRIPT_DIR" build -o "$INSTALL_DIR/service_switcher" .

info "Installing config …"
install -m 0644 "$SCRIPT_DIR/services.json" "$INSTALL_DIR/services.json"

info "Installing systemd unit …"
install -m 0644 "$SCRIPT_DIR/service-switcher.service" "$UNIT_DEST"

info "Reloading systemd and enabling service …"
systemctl daemon-reload
systemctl enable "$UNIT_NAME"
systemctl restart "$UNIT_NAME"

info "service_switcher installed and enabled at boot."
info "  Command socket: nc 127.0.0.1 20100"
info "  Status socket:  nc 127.0.0.1 30100"