---
name: macu-publish
description: "Take a MACU Studio episode all the way to the public site: render it, upload the video to YouTube (unlisted), record the video id, and publish the show bundle to macu-web (the creator's mayorawesome.com-style site). Trigger when the user says 'publish <slug>', 'publish <slug> to the web', 'put <slug> on the site', 'ship <slug>', 'release the episode', or '/macu-publish <slug>'. Guided with confirmations: it auto-runs render + upload + publish, but pauses for the human-only steps (creating a new show on the site, flipping show visibility to Public, and approving the YouTube title/description), and it never makes a video public on YouTube on its own. Works for any show/episode registered in MACU Studio."
trigger: /macu-publish
---

# /macu-publish

Drives a finished MACU Studio episode end-to-end from the local Studio to the public macu-web
site, through the Studio **backend HTTP API** (no clicking in the web UI required for the parts
that have an API). Mirrors the proven flow used to ship the first *As The World Burns* episode.

This skill is **guided**: it runs everything it can automatically, but stops and asks at the few
points a human must act (these have no API on purpose — they're account/ownership decisions):
- Approving the YouTube **title/description** before upload.
- **Creating a new show** on the site (first publish of a brand-new show).
- Flipping the show's **visibility to Public**.
- The final **"make the YouTube video public"** — always left to the user.

## Trigger

- `/macu-publish <slug>` — e.g. `/macu-publish awb-001`.
- Phrases: "publish awb-001 to the web", "ship ep-016", "put it on the site".

`<slug>` is the episode directory name (resolved across all shows via Studio).

## Prerequisites (check first)

```
GET  {STUDIO}/api/health            # Studio up; also returns render_url
GET  {STUDIO}/api/macu-web/status   # {connected:true, base, web} — Studio linked to a macu-web
```
- `{STUDIO}` defaults to `http://127.0.0.1:8774`. If unreachable, honor `MACU_STUDIO_HOST` /
  `MACU_STUDIO_PORT` (or `~/work/macu-pipeline/.env`). The render service (`render_url`, default
  `http://127.0.0.1:8773`) must be up too.
- If `macu-web/status` is **not connected**: the user connects **once per account** (not per show) —
  on any of their shows' Manage pages → *Generate connect token*, then in MACU Studio
  *File → Publish to MACU Web → Connect* and paste it. The token covers all current and future shows.

## Steps

### 1. Render (idempotent — confirms the episode is current)
```
POST {STUDIO}/api/episodes/<slug>/pipeline/run   body: {"from_stage": 2}
```
Capture `job_id`, then poll `GET {STUDIO}/api/jobs/<job_id>` until `job.state` is `done` (or `error`).
Cached stages skip, so a finished episode re-confirms fast. Then verify:
```
GET {STUDIO}/api/episodes/<slug>/final   # {exists:true, size_mb, duration_s, thumb_exists, srt_exists}
```
- **Known failure:** `stage 5 music: 'clip_seconds'` → the manifest `music` block is missing the
  top-level `clip_seconds` key (a hard key in `stage_5_music.py`). Fix by GET-ing the manifest,
  adding `music.clip_seconds` (≈ source-clip length minus a little, e.g. `19.8` for a 20s bed),
  PUT-ing it back, then re-run `from_stage: 5`.

### 2. Upload to YouTube — **unlisted** (pluggable; confirm metadata first)
Draft a title + description appropriate to the show (don't reuse another show's boilerplate), and
**show them to the user for approval** before uploading.

- **If a YouTube uploader is configured on this machine** (the `macu-youtube` skill + its n8n
  webhook — check `~/.claude/skills/macu-youtube/build_payload.py` exists and
  `POST http://localhost:4000/webhook/macu-youtube` is reachable):
  ```
  python3 ~/.claude/skills/macu-youtube/build_payload.py <slug> \
      --description "$(cat blurb.txt)" --tags "tag1, tag2" > /tmp/yt.json   # default privacy=unlisted
  curl -sS --max-time 1800 -X POST http://localhost:4000/webhook/macu-youtube --data @/tmp/yt.json
  ```
  Parse `videoId` from the response. Do **not** pass `--allow-public`.
- **Otherwise (most users):** tell the user to upload the rendered file to their channel as
  **Unlisted** themselves:
  - File: `GET {STUDIO}/api/episodes/<slug>/final/video` or on disk at
    `<episodes_dir>/<slug>/final/<slug>.mp4` (Studio shows `episodes_dir` per show).
  - Then either let Studio **auto-match by title** — `GET {STUDIO}/api/youtube/matches` returns
    episode→video matches (Studio's read-side needs a YouTube API key configured) — or have the
    user paste the watch URL / 11-char id.

### 3. Record the video id in Studio
```
POST {STUDIO}/api/episodes/<slug>/macu-web/youtube   body: {"video_id": "<id-or-url>"}
```
(accepts a bare id or a full YouTube URL → writes `manifest.youtube.video_id`).

### 4. Publish the bundle to macu-web
```
POST {STUDIO}/api/episodes/<slug>/macu-web/published  body: {"published": true}
POST {STUDIO}/api/shows/<show>/publish                body: {"message": "<slug>: publish"}
```
The publish git-pushes the **text bundle** (manifest, show.json, voice names, title templates —
**not** scripts, VO/audio, or video) to the macu-web git remote and triggers a reindex. Resolve
`<show>` from the episode's show id (Studio `GET /api/episodes` is show-scoped; or read `shows.json`).

- **If the push 401s and `GET {publicsite}/show/<show>` is 404:** the show doesn't exist on the site
  yet. **Pause and ask the user to create it** (site → New Show → slug + title). `registerShow` is a
  session-auth action with no API/PAT path. Re-run the publish after they confirm.

### 5. Make it visible (owner-only) + verify
An episode is live only when **episode visibility == PUBLIC AND show visibility == PUBLIC**.
```
GET {STUDIO}/api/episodes/<slug>/macu-web/episode    # {visibility, public, url}
```
- A first publish seeds the **episode** to PUBLIC from `published:true`. If `public:false`, the
  **show** is still gated → **ask the user to set the show to Public** on `{publicsite}/show/<show>/manage`
  (Visibility → Public; also set Share Level if they want episode pages reachable). Owner-only, no API.
- Then verify the live page renders the embed:
  ```
  curl -s {publicsite}/show/<show>/<slug>   # expect HTTP 200, the youtube-nocookie embed, the title
  ```

### 6. (Optional) Push caption tracks
If the user wants subtitles on YouTube and Studio's YouTube OAuth is connected
(`GET {STUDIO}/api/youtube/auth`), upload the SRT: `POST {STUDIO}/api/episodes/<slug>/youtube/captions`.

### 7. Hand off
Keep the YouTube video **unlisted** until the user has eyeballed it on the public site. Report the
YouTube URL + the public episode URL. The user flips the video to **public on YouTube themselves** —
this skill never does.

## Notes / gotchas
- **macu-web may be a remote deploy** (e.g. Fly). Verify "what's live" by fetching the public URL
  from `macu-web/status.web`, not by reading any local macu-web DB/git (which can be a stale dev copy).
- **Scripts stay private** — `publish.py` skips `script.md`, and the public episode page doesn't render
  it. Don't try to surface scripts on the site.
- **Idempotent & re-runnable** — every step is safe to repeat; rendering and publishing skip unchanged work.
- For the *author/render* side of an episode, see `macu-render`; this skill assumes the episode is built.
