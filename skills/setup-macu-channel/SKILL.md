---
name: setup-macu-channel
description: >-
  Wire MACU Studio to Claude Code on THIS machine — the coupling a script can't do.
  Stands up BOTH halves: the chat bridge (chat tile + writers' room, :8802) and the
  TERMINAL drawer (ttyd + tmux running interactive claude, :7682). Generates the
  shared token, installs the user services, tests the loops, surfacing the permission
  prompts to the user. Use when setting up MACU on a new machine, when the Studio chat
  tile says "chat bridge not configured", when the TERMINAL drawer refuses to connect,
  or when the user asks to "set up the macu channel", "connect Studio to Claude Code",
  "wire the chat tile / writers' room / terminal", or runs /setup-macu-channel. Run
  AFTER the rest of the install (deploy/install.sh). Stands up the portable `claude -p`
  bridge (deploy/macu-chat-bridge/) + the ttyd terminal (deploy/macu-ttyd/), NOT a
  full always-on-channels rig.
---

# Set up the MACU ↔ Claude Code coupling

MACU Studio couples to Claude Code in TWO places — this skill stands up both:

1. **Chat tile + writers' room** — POST the operator's message to a bridge on `:8802`,
   which hands it to `claude -p` and POSTs the reply back (Studio long-polls).
   (`deploy/macu-chat-bridge/bridge.py`.)
2. **TERMINAL drawer** (the right-hand slide-in panel) — an iframe to `ttyd` on `:7682`
   serving a `tmux` session running an interactive `claude`. (`deploy/macu-ttyd/`.)

Both need your involvement because they start long-running processes and write config —
approve the steps as they come. Steps 1–6 stand up the bridge; steps 7–9 stand up the
terminal; step 10 wraps up.

> **Scope:** this is for a machine WITHOUT a full always-on-channels rig. If `:8802`
> (and/or `:7682`) is already served by such a rig, leave that part alone — see step 1.
> **Prereqs:** the terminal half needs `ttyd` + `tmux` on PATH (the installer adds them;
> `deploy/doctor.sh` warns if missing).

## Steps

### 1. Don't clobber existing services
Check whether something already answers on the two ports:
`curl -s http://127.0.0.1:8802/health` + `ss -ltn | grep -E ':8802|:7682'`.
- If `:8802` is already served **and** `~/.claude/channels/ss-chat-channel/.env`
  exists with a token, the bridge is already wired (a full channels rig, or a prior
  run) — skip steps 2–6.
- If `:7682` is already served, the terminal is already up — skip steps 7–9.
- If BOTH are up, **stop** — tell the user it's already configured.
- Otherwise continue with whichever half is missing.

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
CLAUDE_BIN="$(command -v claude)"    # ABSOLUTE path — systemd --user PATH omits ~/.local/bin
# systemd --user path:
mkdir -p ~/.config/systemd/user
sed -e "s#__REPO__#$REPO#" -e "s#__CLAUDE_BIN__#$CLAUDE_BIN#" \
  "$REPO/deploy/macu-chat-bridge/macu-chat-bridge.service" \
  > ~/.config/systemd/user/macu-chat-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now macu-chat-bridge
# (fallback if user-systemd is unavailable, e.g. some WSL:
#   MACU_CLAUDE_BIN="$CLAUDE_BIN" nohup python3 "$REPO/deploy/macu-chat-bridge/bridge.py" >~/.macu-chat-bridge.log 2>&1 &  )
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

### 7. Prereq for the terminal: ttyd + tmux
The TERMINAL drawer needs `ttyd` and `tmux` on PATH. `deploy/install.sh` installs
them; if they're missing here, install them (`command -v ttyd tmux` to check):
`sudo apt-get install ttyd tmux` (Debian/Ubuntu/WSL), `sudo dnf install ttyd tmux`
(Fedora), `sudo pacman -S ttyd tmux` (Arch), `brew install ttyd tmux` (macOS). If you
can't, skip steps 7–9 — the bridge half still works; only the drawer won't.

### 8. Stand up the terminal (ttyd)
Render the user unit (substituting the absolute `ttyd`/`claude` paths + a PATH so tmux
and claude resolve under systemd --user), install, enable:
```bash
TTYD_BIN="$(command -v ttyd)"; CLAUDE_BIN="$(command -v claude)"
TTYD_PATH="$(dirname "$CLAUDE_BIN"):$(dirname "$(command -v tmux)"):/usr/local/bin:/usr/bin:/bin"
mkdir -p ~/.config/systemd/user
sed -e "s#__TTYD_BIN__#$TTYD_BIN#" -e "s#__CLAUDE_BIN__#$CLAUDE_BIN#" -e "s#__PATH__#$TTYD_PATH#" \
  "$REPO/deploy/macu-ttyd/macu-ttyd.service" \
  > ~/.config/systemd/user/macu-ttyd.service
systemctl --user daemon-reload
systemctl --user enable --now macu-ttyd
# (fallback if user-systemd is unavailable, e.g. some WSL:
#   nohup "$TTYD_BIN" -W -p 7682 tmux new-session -A -s claude "$CLAUDE_BIN" >~/.macu-ttyd.log 2>&1 &  )
```

### 9. Verify the terminal
```bash
curl -sI http://127.0.0.1:7682/   # -> HTTP/1.1 200
tmux ls                           # -> claude: 1 windows ...
```
If `:7682` answers, open Studio and click **Connect** in the TERMINAL drawer — it
should attach to the claude session.

> **Security:** ttyd here is unauthenticated and serves an interactive Claude session
> (= shell access via Claude's tools). It binds all interfaces by default so the drawer
> works however you reach Studio. For a solo machine, add `-i 127.0.0.1` to the unit's
> ExecStart (loopback); for a shared LAN, add `-c user:pass`. NEVER expose `:7682` on
> the WAN. See `deploy/macu-ttyd/README.md`.

### 10. Done
Tell the user that in Studio the **chat tile**, **writers' room**, AND the **TERMINAL
drawer** now reach their Claude Code. Notes: each chat episode is its own resumed
Claude conversation (session map at `~/.macu-chat-bridge-sessions.json`); the terminal
is a persistent tmux session (survives closing the drawer). Both are loopback/LAN-only
— don't expose `:8802` or `:7682` on the WAN.
