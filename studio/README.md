# MACU Studio

A local, single-user, LAN-only web dashboard around the 8-stage render pipeline in
this repo and the `macu-render` HTTP service (`serve.py` on `:8773`).

- **Backend:** Python 3.11 + FastAPI + uvicorn on **`:8774`**.
- **Frontend:** Vite + React 18 + TypeScript + Tailwind + zustand + @tanstack/react-query.
- **Renders:** the backend does **not** spawn `run.py` itself — it forwards
  `POST /pipeline/run` to the `macu-render` service at `:8773` and re-streams its SSE
  events so the UI can drive per-stage progress.
- **Paths are env-driven** (`config.py` / `lib.py` read a repo-root `.env`): pipeline
  code lives in this repo; episode data lives under `$MACU_SHARES/episodes/<slug>/`.

## Install

See the top-level **[INSTALL.md](../INSTALL.md)** for the full installer. To build just
the app in place: `./scripts/install.sh` (backend venv + frontend build). To run it on
boot, use `sudo ../deploy/install-systemd.sh` (templates the unit to this machine).

## Features

- **Script:** Markdown editor (autosave on blur + Ctrl/Cmd+S), preview that renders cue
  chips in each speaker's color, cue count + runtime estimate, and a chat panel wired to
  a Claude Code session via the chat bridge (see `/setup-macu-channel`; returns a 502
  "not configured" until that's set up).
- **Audio:** per-cue VO rows, playback, regen-single / regen-all-missing, an inspector,
  a voice picker, a Create-Voice (clone) flow, and an SFX panel that fetches CC0 sound
  from Freesound into `assets/sfx/` and appends to `manifest.sfx[]`.
- **Graphics:** title-card grid from `manifest.title_assets`, HyperFrames card render +
  regen, and a spanning-graphics dope sheet.
- **Video:** shot list from `characters` + `broll`, inline seed/prompt editing, per-shot
  master preview, per-shot regen, and render-all-missing.
- **Assembly:** the 8-stage pipeline grid with live SSE, per-stage / full-episode runs,
  re-burn subs, an inline SRT editor, and the final-output player.
- **Manifest drawer:** structured editors for every block + a raw-JSON toggle; atomic
  save via `PUT /api/episodes/{slug}/manifest`.
- **TERMINAL drawer:** an embedded web terminal (`ttyd` + `tmux`) attached to an
  interactive Claude Code session. Like the chat tile, it's part of the Claude Code
  coupling — it needs the ttyd service (`deploy/macu-ttyd/`) which `/setup-macu-channel`
  stands up; until then it will refuse to connect. (Port/session are build-time
  configurable via `VITE_TERMINAL_URL` / `VITE_TERMINAL_PORT` / `VITE_TERMINAL_SESSION`.)

## MCP server (drive Studio from an agent)

Studio exposes its API as **MCP tools** at `http://<host>:8774/mcp` (Streamable
HTTP, stateless, no auth — same LAN-only trust model as the rest of the app).
Any MCP client can write scripts, build manifests, run LLM shot/SFX/card
generation, kick renders, and publish — the whole episode loop, no UI required.

```sh
# Claude Code
claude mcp add --transport http macu-studio http://127.0.0.1:8774/mcp

# Claude Desktop (claude_desktop_config.json)
{ "mcpServers": { "macu-studio": {
    "command": "npx",
    "args": ["-y", "mcp-remote@latest", "http://<host>:8774/mcp", "--allow-http"] } } }
```

27 tools, designed to hand-hold smaller models: call `studio_overview` first —
it returns the shows, what's connected, and a step-by-step workflow guide
(create episode → write script → manifest → shots → render → publish). All
`generate_*` tools are dry-runs unless `apply=true`; every error carries a
`hint` with the next thing to try. Implementation: `backend/macu_studio/mcp_server.py`
calls the REST routes in-process (httpx `ASGITransport`), so tools can never
drift from the UI's behavior.

## Dev loop

```sh
.venv/bin/uvicorn macu_studio.main:app --reload --host 0.0.0.0 --port 8774   # one terminal
cd frontend && npm run dev                                                   # another
```

The Vite dev server runs on `:5173` and proxies `/api` to `:8774`, so the UI hot-reloads
while the backend keeps running.

## Endpoints

Studio API (under `/api`):

| Method & path                                  | Returns                                        |
| ---------------------------------------------- | ---------------------------------------------- |
| `GET /api/health`                              | `{ok, episodes_dir, render_url}`               |
| `GET /api/episodes`                            | `{ episodes: EpisodeSummary[] }`               |
| `GET /api/episodes/{slug}/manifest`            | raw manifest JSON                              |
| `PUT /api/episodes/{slug}/manifest`            | atomic write                                   |
| `GET /api/episodes/{slug}/cues`                | derived cue rows (status, voice, …)            |
| `GET /api/episodes/{slug}/shots`               | character + b-roll keys                        |
| `GET /api/episodes/{slug}/titles`              | title-asset table + HyperFrames drafts         |
| `GET /api/episodes/{slug}/pipeline`            | 8-stage at-rest status snapshot                |
| `GET /api/episodes/{slug}/final`               | `{exists, size_mb, duration_s, ...}`           |
| `GET/PUT /api/episodes/{slug}/srt`             | parsed entries + raw text / rewrite            |
| `GET/PUT /api/episodes/{slug}/script`          | script.md text / rewrite                       |
| `POST /api/episodes/{slug}/pipeline/run`       | `{from_stage?, only?}` → forwards to :8773     |
| `POST /api/episodes/{slug}/cue/{id}/regen`     | drops `vo/<id>.wav` + sidecar → `only=1`       |
| `POST /api/episodes/{slug}/shot/{key}/regen`   | drops `clips/<key>_master.zs.webp` → `from=2`  |
| `POST /api/episodes/{slug}/sfx/fetch`          | runs `freesound_fetch.py`, appends to `manifest.sfx[]` |
| `POST /api/episodes/{slug}/chat`               | proxies to the chat bridge (long-polled reply) |
| `GET /api/jobs/{job_id}/stream`                | SSE proxy from `macu-render :8773`             |

Static media (used by `<audio>`/`<video>` directly):

| Path                                           | Streams                                        |
| ---------------------------------------------- | ---------------------------------------------- |
| `/api/episodes/{slug}/cue/{cue_id}/audio`      | `vo/<cue_id>.wav`                              |
| `/api/episodes/{slug}/shot/{key}/preview`      | `clips/<key>_master.zs.webp`                   |
| `/api/episodes/{slug}/title/{key}/preview`     | `titles/<key>.mp4`                             |
| `/api/episodes/{slug}/final/video`             | `final/<slug>.mp4` (Range-aware)               |
| `/api/episodes/{slug}/final/thumb`             | `final/<slug>_thumbs.jpg`                      |
