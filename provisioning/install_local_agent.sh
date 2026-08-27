#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Local package-free diagnostics agent installer
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
set -euo pipefail

APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true
[[ $EUID -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET=/opt/hydra-umc/os-agent
SERVICE_USER=hydra-umc-agent

run() { if $APPLY; then "$@"; else printf '[dry-run] '; printf '%q ' "$@"; printf '\n'; fi; }
if $APPLY && ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Missing $SERVICE_USER. Run provisioning/first_boot.sh --apply first." >&2
  exit 2
fi
run install -d -o root -g root -m 0755 "$TARGET"
run install -d -o root -g "$SERVICE_USER" -m 0750 /etc/hydra-umc
run cp -a "$ROOT/agent/src/hydra_umc_os" "$TARGET/"
run chown -R root:root "$TARGET/hydra_umc_os"
run chmod -R go-w "$TARGET/hydra_umc_os"
run install -m 0644 "$ROOT/systemd/hydra-umc-agent.service" /etc/systemd/system/hydra-umc-agent.service
if $APPLY && [[ ! -f /etc/hydra-umc/config.json ]]; then
  install -m 0640 -o root -g "$SERVICE_USER" "$ROOT/config/hydra-umc-os.example.json" /etc/hydra-umc/config.json
fi
if $APPLY; then
  cat >/usr/local/bin/hydra-umc-agent <<'EOF'
#!/usr/bin/env sh
export PYTHONPATH=/opt/hydra-umc/os-agent
exec /usr/bin/python3 -m hydra_umc_os.agent "$@"
EOF
  chmod 0755 /usr/local/bin/hydra-umc-agent
fi
run systemctl daemon-reload
echo "Agent installed. Review config, then enable manually: systemctl enable --now hydra-umc-agent"
