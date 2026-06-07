---
name: setup-macu-channel
description: >-
  Wire MACU Studio's chat tile + writers' room to Claude Code on THIS machine —
  the coupling a script can't do (it generates a shared token, starts the chat
  bridge, and tests the loop, surfacing the permission prompts to the user). Use
  when setting up MACU on a new machine (e.g. Leo) and the Studio chat tile says
  "chat bridge not configured", or when the user asks to "set up the macu channel",
  "connect Studio to Claude Code", "wire the chat tile / writers' room", or runs
  /setup-macu-channel. Run AFTER the rest of the install (deploy/install.sh). This
  stands up the portable `claude -p` bridge (deploy/macu-chat-bridge/), NOT the
  full Second Shift always-on-channels rig.
---

# Set up the MACU ↔ Claude Code channel

MACU Studio's **chat tile** and **writers' room** work by POSTing the operator's
message to a bridge on `:8802`, which hands it to a Claude Code session and POSTs
the reply back (Studio long-polls for it). This skill stands up the portable
bridge (`deploy/macu-chat-bridge/bridge.py` — just `claude -p` headless) and wires
the shared secret. It needs your involvement because it starts a long-running
process and writes config — approve the steps as they come.

> **Scope:** this is for a machine WITHOUT the Second Shift always-on-channels rig.
> If `:8802` is already served by that rig (as on Max), do nothing — see step 1.

## Steps

### 1. Don't clobber an existing bridge
Check whether something already answers on `:8802`:
`curl -s http://127.0.0.1:8802/health` and `ss -ltn | grep 8802`.
- If a server is already there **and** `~/.claude/channels/ss-chat-channel/.env`
  exists with a token, this machine is already wired (Max's full rig, or a prior
  run). **Stop** — tell the user it's already configured; nothing to do.
- Otherwise continue.

### 2. Prereq: the `claude` CLI
Confirm `claude --version` works and the user is logged in (the bridge runs
`claude -p` as them). If missing, stop and point them to install/login to Claude
Code first.

### 3. Shared token
Both Studio (`config.py` `_load_chat_token`) and the bridge read
`~/.claude/channels/ss-chat-channel/.env`. Ensure it has a token:
```bash
mkdir -p ~/.claude/channels/ss-chat-channel
[ -f ~/.claude/channels/ss-chat-channel/.env ] || \
  printf 'SS_CHAT_WEBHOOK_TOKEN=%s\n' "$(openssl rand -hex 24)" \
    > ~/.claude/channels/ss-chat-channel/.env
chmod 600 ~/.claude/channels/ss-chat-channel/.env
```
Studio's defaults already point `MACU_CHAT_CHANNEL_URL` at `http://localhost:8802/`,
so no Studio config edit is needed beyond this token.

### 4. Start the bridge
Prefer a **systemd --user** service so it survives logout; fall back to `nohup`
where user-systemd isn't available (e.g. some WSL setups).
```bash
REPO="$(cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" && pwd)"   # the macu-pipeline checkout
# systemd --user path:
mkdir -p ~/.config/systemd/user
sed "s#__REPO__#$REPO#" "$REPO/deploy/macu-chat-bridge/macu-chat-bridge.service" \
  > ~/.config/systemd/user/macu-chat-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now macu-chat-bridge
# (fallback if the above fails:  nohup python3 "$REPO/deploy/macu-chat-bridge/bridge.py" >~/.macu-chat-bridge.log 2>&1 &  )
```
Then verify: `curl -s http://127.0.0.1:8802/health` → `{"ok": true, ...}`.

### 5. Restart Studio so it reads the token
If Studio is already running, restart it (`systemctl restart macu-studio` if
installed as a service, or restart the uvicorn process) so `config.py` picks up
`SS_CHAT_WEBHOOK_TOKEN`.

### 6. Test the round-trip
Confirm `claude -p` works headless and the bridge relays. Quick end-to-end check
with a throwaway reply-catcher:
```bash
# tiny catcher on :8899 that prints whatever the bridge POSTs back
python3 - <<'PY' &
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(s):
        n=int(s.headers.get('Content-Length',0)); print('REPLY:', s.rfile.read(n).decode()); s.send_response(200); s.end_headers()
    def log_message(s,*a): pass
HTTPServer(('127.0.0.1',8899),H).handle_request()
PY
TOKEN=$(grep -h SS_CHAT_WEBHOOK_TOKEN ~/.claude/channels/ss-chat-channel/.env | cut -d= -f2)
curl -s -X POST http://127.0.0.1:8802/ -H "X-Webhook-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"request_id":"test1","session_id":"setup-test","text":"Reply with exactly: bridge ok","reply_url":"http://127.0.0.1:8899/"}'
# wait a few seconds for the catcher to print REPLY: {"request_id":"test1","text":"bridge ok"}
```
If `REPLY:` shows the answer, the loop works.

### 7. Done
Tell the user the **chat tile** and **writers' room** in Studio now reach their
Claude Code. Note: each episode is its own resumed Claude conversation (session
map at `~/.macu-chat-bridge-sessions.json`); the bridge is loopback-only and
token-gated — don't expose `:8802`.
