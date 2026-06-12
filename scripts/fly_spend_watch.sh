#!/usr/bin/env bash
# Fly.io cost-drift watcher. Fly exposes no live $ figure via API/CLI, so this
# checks the things that actually cause a surprise bill: extra machines, a bigger
# VM size, or unexpected/larger volumes. Prints "OK" + inventory when nothing has
# drifted from the known-good baseline; prints "DRIFT" + the offending lines when it has.
# August's own $50 budget alert (fly.io dashboard) owns the dollar threshold.
set -euo pipefail
export PATH="$HOME/.fly/bin:$PATH"
ENV="${MACU_PIPELINE_ENV:-/home/mayorawesome/work/macu-pipeline/.env}"
[ -f "$ENV" ] && { set -a; . "$ENV"; set +a; }
TOK="${FLY_API_TOKEN:-${FLY_ACCESS_TOKEN:-}}"
[ -n "$TOK" ] || { echo "DRIFT: no Fly token (check $ENV)"; exit 1; }

# Baseline: app -> "machines|size|volumes" expected counts/values.
declare -A EXPECT=(
  [macu-web]="1|shared-cpu-1x:2048MB|1"
  [macu-demo]="1|shared-cpu-1x:256MB|0"
)

drift=0
report=""
for app in macu-web macu-demo; do
  IFS='|' read -r exp_m exp_size exp_vol <<<"${EXPECT[$app]}"
  ml="$(flyctl machine list -a "$app" -t "$TOK" 2>/dev/null || true)"
  vl="$(flyctl volumes list -a "$app" -t "$TOK" 2>/dev/null || true)"
  # data rows have a fdaa: IPv6 (machines) / vol_ id (volumes)
  n_m="$(printf '%s\n' "$ml" | grep -c 'fdaa:' || true)"
  n_v="$(printf '%s\n' "$vl" | grep -c 'vol_' || true)"
  sizes="$(printf '%s\n' "$ml" | grep -oE 'shared-cpu-[0-9]x:[0-9]+MB|performance-[0-9]+x:[0-9]+MB' | sort -u | tr '\n' ',' )"
  line="$app: machines=$n_m size=${sizes%,} volumes=$n_v"
  if [ "$n_m" != "$exp_m" ] || [ "$n_v" != "$exp_vol" ] || [ "${sizes%,}" != "$exp_size" ]; then
    drift=1; report+="  DRIFT $line (expected machines=$exp_m size=$exp_size volumes=$exp_vol)"$'\n'
  else
    report+="  ok    $line"$'\n'
  fi
done

if [ "$drift" = 1 ]; then
  printf 'DRIFT\n%s' "$report"
  exit 2
fi
printf 'OK\n%s' "$report"
