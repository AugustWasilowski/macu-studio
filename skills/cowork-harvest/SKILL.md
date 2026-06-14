---
name: cowork-harvest
description: "Work the MACU Studio CoWork job-board: claim browser-generation jobs, make them FREE in the Higgsfield web app (the unlimited web tier the API can't reach), and report the result generation ids back so Studio auto-harvests them into the episode. For a browser-capable CoWork agent connected to a Studio install's MCP. Trigger when the user says 'work the CoWork queue', 'harvest Higgsfield jobs', '/cowork-harvest', or when there are pending jobs on the board. The $0 generation loop: Leo/August queue work → CoWork generates it free in the browser → Studio files the results automatically."
trigger: /cowork-harvest
---

# /cowork-harvest

You are the **browser hands** of the MACU Studio pipeline. Higgsfield's "unlimited"
generation tiers are **web-app only** — the API always bills. You can drive the web
app; the API/CLI agents (Leo) can't. So they **queue** generation jobs on the Studio
job-board, you **execute** them free in the browser, and Studio **auto-harvests** the
results into the episode. No files are hand-passed.

## Prerequisites

- You are connected to a MACU Studio install's MCP server (the `cowork_*` tools are
  available). If they aren't, the user needs to add the Studio MCP
  (`http://<studio-host>:8774/mcp`) to your client. No token/auth — it's LAN-only.
- You are signed in to the Higgsfield **web app** in your browser, on an account
  whose unlimited tier covers the models the jobs ask for.

## The loop

Repeat until the queue has no pending jobs:

1. **Claim** the next job:
   `cowork_job_claim()` (optionally `episode=` / `kinds=["video"]`). It atomically
   flips the oldest pending job to `claimed` and returns it, or `{job: null}` when
   the queue is empty. (Or browse first with `cowork_jobs_list(status="pending")`.)

2. **Mark it running** so the Studio queue panel reflects reality:
   `cowork_job_update(id, status="in_progress")`.

3. **Generate it in the Higgsfield web app.** Read the job's fields:
   - `prompt` — use verbatim (the show's style suffix is already folded in).
   - `model` — the requested model (e.g. `hailuo_2_3`, `nano_banana`); pick it in the UI.
   - `kind` — `still` (image gen), `video` (video gen), or `soul` (train a Soul).
   - `params` — may carry `seed`, `duration_s`, `input_still` (a start-frame to upload), `soul_id`, etc.
   Drive the browser to produce it. **Use the unlimited/free path** — follow the
   **`higgsfield-web-free-gen`** skill for exactly how (the Unlimited toggle, the
   model-label traps, and how to verify you weren't billed). Generation is browser
   clicks only; never use the MCP `generate_*` tools (they cost credits).

4. **Find the generation id** you just made:
   `cowork_recent_generations(type="video")` → returns the account's newest
   generations as `{id, type, model, prompt, thumb_url, created_at}`. Match the one
   you just created (by prompt/model/recency) and take its **`id`**.

5. **Complete the job** — one call attaches the result and triggers the harvest:
   `cowork_job_complete(id, gen_ids=["<that generation id>"])`.
   Studio downloads the result (free) and files it into the job's episode target
   automatically — a character/b-roll **seed still** or a **shot clip**, with
   provenance. You're done with that job.

6. If you **couldn't** make it (NSFW block, model unavailable, etc.):
   `cowork_job_update(id, status="failed", error="<short reason>")`, or
   `status="skipped"` to pass. The operator can re-queue it later.

## The one rule that matters

**`gen_ids` are Higgsfield GENERATION IDs, not media URLs.** Studio harvests by
calling the generation by id and reading its result media. If you pass a URL or a
job-claim id, the harvest finds nothing. Always pull the id from
`cowork_recent_generations` (or the HF account history) — that's what step 4 is for.

## Per-kind notes

- **still** — an image gen. Target is `character:<key>` or `broll:<key>`; it lands as
  the episode's `stills/<key>.png` seed still.
- **video** — a video gen. Target is `shot:<shot_id>`; it lands as `clips/hf_<shot_id>.mp4`.
  If `params.input_still` is set, upload that as the start frame (i2v).
- **soul** — train a Soul in the web app, then report the trained id with
  `cowork_job_update(id, status="done", result_json='{"soul_id":"<id>"}')`. There's
  no media to harvest for a soul job.

## Tools (Studio MCP)

| Tool | Use |
|---|---|
| `cowork_jobs_list(status, episode, kind)` | See the queue (default `status="pending"`). |
| `cowork_job_claim(episode, kinds, by)` | Atomically take the oldest pending job. |
| `cowork_job_update(id, status, result_gen_ids, note, error, result_json)` | Report progress / failure / soul result. |
| `cowork_recent_generations(type, limit)` | Find the id of what you just made. |
| `cowork_job_complete(id, gen_ids, note)` | One-call done + harvest (the happy path). |
| `cowork_jobs_create(episode, jobs_json)` | Queue work (usually Leo/August do this, not you). |

## Etiquette

- One job at a time per the claim → complete cycle; don't claim a batch you won't finish.
- Keep `note`/`error` short and human — they show in the Studio queue panel.
- Don't re-complete an already-`done` job; to re-harvest, the operator sets it back to
  `pending` (the panel's ↺) and you claim it fresh.

See `reference/job-contract.md` for the full job schema, status lifecycle, and
placement semantics.
