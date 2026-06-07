# MACU terminal (ttyd + tmux)

Backs Studio's right-hand **TERMINAL drawer** — an embedded web terminal attached to a
persistent `tmux` session running an interactive Claude Code (`claude`). It's the
visible half of the Studio↔Claude coupling (the other half is the chat bridge in
`../macu-chat-bridge/`).

This is **optional** — only the TERMINAL drawer needs it. The `setup-macu-channel`
skill stands it up alongside the chat bridge; you don't normally touch these files by
hand.

## What runs

`ttyd -W -p 7682 tmux new-session -A -s claude claude` — ttyd serves a writable web
terminal on `:7682`; the page attaches to (or creates) a tmux session named `claude`
that runs `claude`. tmux gives persistence: close the drawer, reopen, same session.

## Setup / verify

The skill renders `macu-ttyd.service` (substituting absolute `ttyd`/`claude` paths and
a PATH) into `~/.config/systemd/user/` and enables it. Manually:

```bash
command -v ttyd tmux            # both must be installed (the installer does this)
systemctl --user status macu-ttyd
curl -sI http://127.0.0.1:7682/ # -> HTTP/1.1 200
tmux ls                         # -> claude: 1 windows ...
```

If user-systemd isn't available (some WSL setups), the skill launches it under nohup
instead:

```bash
nohup ttyd -W -p 7682 tmux new-session -A -s claude claude >~/.macu-ttyd.log 2>&1 &
```

## Security

ttyd here has **no auth** and serves an interactive Claude session — i.e. shell access
(via Claude's tools) to anyone who can reach `:7682`. It therefore ships
**loopback-only** (`-i 127.0.0.1` in the unit): reachable from the machine running
Studio — including WSL from the Windows host, via localhost forwarding — but **not**
from the LAN. The frontend default targets `127.0.0.1:7682` to match.

To use the drawer from **another machine over the LAN**:

1. Remove `-i 127.0.0.1` from the unit's ExecStart (and add `-c user:pass` for HTTP
   basic auth — strongly recommended, since this is shell access).
2. Rebuild the SPA with `VITE_TERMINAL_URL=http://<lan-host>:7682/`.

**Never** expose `:7682` on the public internet. Studio is LAN-only by design.

## Customizing the port / session

The drawer's URL + session name are build-time configurable in the frontend
(`VITE_TERMINAL_URL` / `VITE_TERMINAL_PORT` / `VITE_TERMINAL_SESSION`). If you change
the port or tmux session name here, set the matching VITE var and rebuild the SPA.
