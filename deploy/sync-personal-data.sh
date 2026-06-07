#!/usr/bin/env bash
# OPTIONAL — copy your OWN MACU data from an existing box (e.g. Max) to this one.
# This is NOT part of the shareable installer; it moves YOUR cloned voices and
# asset kits so a second machine you own matches your setup exactly.
#
# Usage:  deploy/sync-personal-data.sh <ssh-source>
#   e.g.  deploy/sync-personal-data.sh mayorawesome@max
#         deploy/sync-personal-data.sh mayorawesome@bigshoulder-server.finch-hake.ts.net
#
# Copies (rsync over ssh; assumes the source uses the same /mnt/storage layout —
# adjust SRC_DATA_ROOT/SRC_SHARES below if not):
#   - OmniVoice profile store  -> exact same voices AND profile_ids (so shows.json
#     / manifest speaker_map entries resolve unchanged). ~4.6 GB.
#   - MACU asset kits (music / sfx / titles).
# It does NOT copy episodes (your scripts/manifests come from the git repo) or the
# big render artifacts.
set -euo pipefail

SRC="${1:-}"
[ -z "$SRC" ] && { echo "usage: $0 <ssh-source>   e.g. mayorawesome@max"; exit 2; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"; set +a
: "${MACU_DATA_ROOT:=/mnt/storage}"
: "${MACU_SHARES:=/mnt/storage/shares/MACU}"

# Source-side layout (Max defaults; override via env if the source differs).
SRC_DATA_ROOT="${SRC_DATA_ROOT:-/mnt/storage}"
SRC_SHARES="${SRC_SHARES:-/mnt/storage/shares/MACU}"

RS="rsync -ah --info=progress2 --partial"

echo "=== OmniVoice voice store (state + data) — exact voices/ids ==="
mkdir -p "$MACU_DATA_ROOT/omnivoice"
$RS "$SRC:$SRC_DATA_ROOT/omnivoice/state/"  "$MACU_DATA_ROOT/omnivoice/state/"
$RS "$SRC:$SRC_DATA_ROOT/omnivoice/data/"   "$MACU_DATA_ROOT/omnivoice/data/"
# hf-cache (base model) is optional — it re-downloads on first inference; uncomment to copy:
# $RS "$SRC:$SRC_DATA_ROOT/omnivoice/hf-cache/" "$MACU_DATA_ROOT/omnivoice/hf-cache/"

echo "=== MACU asset kits (music / sfx / titles) ==="
mkdir -p "$MACU_SHARES/assets"
for kit in music sfx titles; do
  $RS "$SRC:$SRC_SHARES/assets/$kit/" "$MACU_SHARES/assets/$kit/" || true
done

echo "=== done. Restart omnivoice so it picks up the copied profile store: ==="
echo "  docker restart omnivoice   (or it'll start on the next clone/generate)"
