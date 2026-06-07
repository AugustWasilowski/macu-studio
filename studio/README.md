# MACU Studio

A local, single-user, LAN-only production dashboard for *The MACU Report*.
A UI shell around the 8-stage pipeline in this repo + the `macu-render` HTTP
service (`serve.py` on `:8773`).

- **Backend:** Python 3.11 + FastAPI + uvicorn on **`:8774`** (`0.0.0.0`).
- **Frontend:** Vite + React 18 + TypeScript + Tailwind + zustand + @tanstack/react-query.
- **Renders:** the studio backend does **not** spawn `run.py`. It forwards
  `POST /pipeline/run` to the existing `macu-render` service at `:8773` and
  re-streams its SSE events so the UI can drive the per-stage progress.
- **Source of truth for pipeline code:** this repo at `/mnt/storage/macu-pipeline/pipeline/`
  (`/mnt/storage/shares/MACU/pipeline` is a back-compat symlink to it). Studio doesn't
  invoke the scripts directly — it drives them through the `:8773` render service.
- **Source of truth for episode data:** `/mnt/storage/shares/MACU/episodes/<slug>/`.

The visual design lives at
`/mnt/storage/shares/MACU/design_handoff_macu_studio/` — open
`design/MACU Studio.html` in a browser to interact with the original prototype.

## What works (v0.7)

- App shell: episode switcher, hash routing (`#<slug>/<stage>`), CRT scanlines, live clock.
- **Stage 1 — Script:** resizable split. Markdown editor with autosave on blur + Ctrl/Cmd+S, preview mode that renders cue chips (`[CUE id / SPEAKER]`) in the speaker's color, status bar with cue count + estimated runtime. Chat-with-Max panel (currently a stub — message goes to backend, gets a canned reply; real ss-chat-channel proxy is the only deferred item).
- **Stage 2 — Audio:** per-cue VO rows with speaker pills, seeded oscilloscope waveforms, `<audio>` playback via the streaming endpoint, regen-single-cue (deletes wav + sidecar entry, fires `--only 1`), regen-all-missing (staggered). Inspector pane with full cue metadata. SFX panel with **working Add SFX dialog**: posts to `/api/episodes/{slug}/sfx/fetch` → backend shells `freesound_fetch.py` → CC0 wav lands in `assets/sfx/` and a new entry is appended to `manifest.sfx[]`.
- **Stage 3 — Graphics:** title-card grid populated from `manifest.title_assets`. Per-episode cards (`episodes/<slug>/titles/<key>.mp4`) auto-play in their tiles via the streaming endpoint. Shared `assets/titles/` entries show a `REUSE` badge. HyperFrames .html drafts surfaced in a strip below. Per-card regen button currently returns 501 with a hint about `npx hyperframes render`.
- **Stage 4 — Video:** shot list from `characters` + `broll`. Inline-editable per-shot seed (writes back to manifest on blur, marks shot stale). Inspector pane with current `.zs.webp` preview (server streams Chromium-compatible webp directly), inline prompt editor that writes to manifest. Per-shot regen drops the master + RIFE dir then fires `--from 2`. Render-all-missing button on the header.
- **Stage 5 — Assembly:** 8-row pipeline grid with derived at-rest status + live SSE overlay. Per-stage **▶ Run**, "Run from", **RENDER FULL EPISODE**, "Re-burn subs only". Live log tail from SSE. Inline SRT row editor. Final-output player + size/duration/thumb strip + download + path copy.
- **Manifest drawer** (open via the brace `{ }` button in topbar): collapsible sections for Episode metadata, Voice (`default` + `speaker_map` table — engine select, speed, voice_name, profile_id), ComfyUI, Style, Characters (per-character seed + core prompt), Music (toggle + clips list with add/remove), Subtitles, SFX (link to Stage 2). **Raw JSON toggle** for direct editing. Atomic save via `PUT /api/episodes/{slug}/manifest`.

Open follow-ups:
- Real chat: replace the stub in `Script.tsx` ↔ `/api/episodes/{slug}/chat` with an actual proxy through `ss-chat-channel` MCP.
- HyperFrames title regen: needs an explicit per-episode composition convention before wiring it.
- Cloudflare Access for public exposure (LAN-only for now).

## Install

```sh
./scripts/install.sh
# Then, manually (COPY the unit, don't symlink — the repo lives on /mnt/storage,
# which isn't mounted when systemd loads units at early boot; the unit must be on /):
sudo cp $(pwd)/systemd/macu-studio.service /etc/systemd/system/macu-studio.service
sudo systemctl daemon-reload
sudo systemctl enable --now macu-studio
sudo touch /var/log/macu-studio.log && sudo chown mayorawesome:mayorawesome /var/log/macu-studio.log
```

Then open <http://127.0.0.1:8774/>.

## Dev loop

In one terminal:
```sh
.venv/bin/uvicorn macu_studio.main:app --reload --host 0.0.0.0 --port 8774
```

In another:
```sh
cd frontend && npm run dev
```

The Vite dev server runs on `:5173` and proxies `/api` to `:8774`, so you can
hot-reload the UI while the backend keeps running.

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
| `GET /api/episodes/{slug}/srt`                 | parsed entries + raw text                      |
| `PUT /api/episodes/{slug}/srt`                 | rewrite SRT                                    |
| `GET /api/episodes/{slug}/script`              | script.md text                                 |
| `PUT /api/episodes/{slug}/script`              | rewrite script.md                              |
| `POST /api/episodes/{slug}/pipeline/run`       | `{from_stage?, only?}` → forwards to :8773     |
| `POST /api/episodes/{slug}/cue/{id}/regen`     | drops `vo/<id>.wav` + sidecar → `only=1`       |
| `POST /api/episodes/{slug}/shot/{key}/regen`   | drops `clips/<key>_master.zs.webp` → `from=2`  |
| `POST /api/episodes/{slug}/sfx/fetch`          | `{query, cue_id?, at?, duration_max?, basename?, license?}` → runs `freesound_fetch.py` and appends to `manifest.sfx[]` |
| `DELETE /api/episodes/{slug}/sfx?file=...`     | removes a single `manifest.sfx[]` entry (does not delete wav) |
| `POST /api/episodes/{slug}/chat`               | stub — returns a canned reply                  |
| `GET /api/jobs/{job_id}/stream`                | SSE proxy from `macu-render :8773`             |
| `GET /api/jobs/{job_id}`                       | snapshot pass-through                          |

Static media (used by `<audio>`/`<video>` directly):

| Path                                           | Streams                                        |
| ---------------------------------------------- | ---------------------------------------------- |
| `/api/episodes/{slug}/cue/{cue_id}/audio`      | `vo/<cue_id>.wav`                              |
| `/api/episodes/{slug}/shot/{key}/preview`      | `clips/<key>_master.zs.webp`                   |
| `/api/episodes/{slug}/title/{key}/preview`     | `titles/<key>.mp4`                             |
| `/api/episodes/{slug}/final/video`             | `final/<slug>.mp4` (Range-aware)               |
| `/api/episodes/{slug}/final/thumb`             | `final/<slug>_thumbs.jpg`                      |

## Cloudflare Access

Public at <https://studio.mayorawesome.com> — tunneled through `n8n-mcp` to `localhost:8774`, gated by the
Cloudflare Access app `2ace1626` (references the reusable "August" policy `4f76c12b-71ad-42e0-8216-a86de3c66828`),
same pattern as `memos.mayorawesome.com` / `jellyfin.mayorawesome.com`. Added 2026-06-03. LAN access stays at
`http://127.0.0.1:8774/`.
