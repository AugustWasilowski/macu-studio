#!/usr/bin/env bash
# Install the macu-render + macu-studio systemd units, substituting THIS machine's
# repo path / shares dir / run user into the templates. Run with sudo.
#
#   sudo ./deploy/install-systemd.sh
#   sudo systemctl enable --now macu-render macu-studio
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"
[ -f "$REPO/deploy/services/.env" ] && . "$REPO/deploy/services/.env"; set +a

: "${MACU_SHARES:=/mnt/storage/shares/MACU}"
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_GROUP="$(id -gn "$RUN_USER")"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo (writes to /etc/systemd/system)." >&2
  exit 1
fi
if [ ! -x "$REPO/studio/.venv/bin/python" ]; then
  echo "Studio venv not built yet — run ./deploy/install.sh first." >&2
  exit 1
fi

subst() {  # template -> stdout, with this machine's values
  sed -e "s#__REPO__#${REPO}#g" \
      -e "s#__SHARES__#${MACU_SHARES}#g" \
      -e "s#__USER__#${RUN_USER}#g" \
      -e "s#__GROUP__#${RUN_GROUP}#g" "$1"
}

subst "$REPO/deploy/macu-render.service"         > /etc/systemd/system/macu-render.service
subst "$REPO/studio/systemd/macu-studio.service" > /etc/systemd/system/macu-studio.service
touch /var/log/macu-render.log /var/log/macu-studio.log
chown "$RUN_USER":"$RUN_GROUP" /var/log/macu-render.log /var/log/macu-studio.log
systemctl daemon-reload

cat <<EOF
Installed units for user '${RUN_USER}', repo '${REPO}'.
  start now + on boot:  sudo systemctl enable --now macu-render macu-studio
  stop:                 sudo systemctl stop macu-render macu-studio
  disable on boot:      sudo systemctl disable macu-render macu-studio
EOF
