# MACU chat bridge

The portable coupling between **MACU Studio's chat tile / writers' room** and
**Claude Code**. Studio POSTs a message to a bridge on `:8802`; the bridge runs
`claude -p` headless and POSTs the reply back. That's the whole loop.

`bridge.py` is a stdlib-only server whose only dependency is the **`claude` CLI**
(logged in). It is the shareable alternative to the Second Shift always-on
channels rig that drives this on Max — same wire protocol, far less to stand up.

## Setup

Run **`/setup-macu-channel`** in Claude Code — it generates the shared token,
writes it where both Studio and the bridge read it
(`~/.claude/channels/ss-chat-channel/.env`), starts the bridge, and tests the
round-trip.

Manual equivalent:
```bash
# 1. shared token (both sides read this file)
mkdir -p ~/.claude/channels/ss-chat-channel
printf 'SS_CHAT_WEBHOOK_TOKEN=%s\n' "$(openssl rand -hex 24)" \
  > ~/.claude/channels/ss-chat-channel/.env && chmod 600 ~/.claude/channels/ss-chat-channel/.env
# 2. run the bridge (foreground; or use the systemd --user unit here)
python3 deploy/macu-chat-bridge/bridge.py
# 3. restart Studio so it picks up the token
```

Studio defaults already point at `http://localhost:8802/` (`MACU_CHAT_CHANNEL_URL`)
and read the same token, so no Studio config change is needed.

## Notes
- Per Studio `session_id` (one per episode), the bridge `--resume`s a Claude
  session, so each episode's chat is one continuous conversation. Session map:
  `~/.macu-chat-bridge-sessions.json`.
- Bound to loopback only; the token gates POSTs. Don't expose `:8802` publicly.
- **Max already runs the full rig** on `:8802` — there the bridge is unnecessary
  (the setup skill detects this and leaves it alone).
