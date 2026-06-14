# CoWork ↔ Studio job-board — contract reference

The full contract behind the `cowork-harvest` skill (SSA-133). The store + REST are
in `studio/backend/macu_studio/cowork_jobs.py` + `routes_cowork.py`; the `cowork_*`
MCP tools + auto-harvest are in `mcp_server.py`. Persistence:
`~/.config/macu-studio/cowork_jobs.json` (per Studio install; override `MACU_COWORK_JOBS`).

## Why this exists

Higgsfield's unlimited generation tiers are **web-app only** — every API generation
bills (nano_banana = 2 cr/image, Hailuo 2.3 6s = 6 cr, confirmed). A browser-capable
CoWork agent reaches the unlimited tier; the API/CLI agents don't. The job-board lets
them divide the work: queue (API side) → generate free (CoWork in the browser) →
harvest (Studio downloads + files the result; listing + download are free API ops).

## Job schema

```jsonc
{
  "id": "j-XXXXXXXX",                 // assigned by the store
  "episode": "ep-022",
  "kind": "still" | "video" | "soul",
  "target": "<type>:<id>",            // character:ron | broll:evidence_table |
                                      //   shot:c01_s1 | soul:macu_ron
  "prompt": "...",                    // show style suffix already folded in — use verbatim
  "model": "nano_banana" | "hailuo_2_3" | "...",  // advisory; pick it in the web UI
  "params": { "seed": 77777, "duration_s": 6, "input_still": "...", "soul_id": "..." },
  "status": "pending|claimed|in_progress|done|failed|skipped",
  "claimed_by": "cowork" | null,
  "result_gen_ids": ["<higgsfield generation id>"],  // what you report; harvest input
  "result": { "soul_id": "..." },     // freeform structured result (soul jobs)
  "note": "", "error": null,
  "created_at": "<iso utc>", "updated_at": "<iso utc>"
}
```

## Status lifecycle

```
pending ──claim──▶ claimed ──▶ in_progress ──▶ done       (success → harvest fires)
                                            ├─▶ failed     (couldn't generate)
                                            └─▶ skipped    (passed over)
```

- Set `in_progress` while generating so the Studio queue panel shows it running.
- `done` is the **only** status that triggers placement, and only on a *fresh*
  transition into `done` (re-PATCHing an already-done job does nothing). To
  re-harvest, the operator sets it back to `pending` (panel ↺) and you re-claim.

## What `result_gen_ids` must be

The **Higgsfield generation id** — the id under which the generation lives in the
account history. Placement runs `fetch_generation(gen_id)`, which reads
`generation.results.rawUrl` (the output media) — **not** `params.input_image` (the
start frame) and **not** a media URL you paste. Get the id from:

- `cowork_recent_generations(type=...)` (Studio MCP — the easy path), or
- the Higgsfield account history directly (`show_generations`, newest-first), or
- Studio's `GET /api/higgsfield/generations`.

If multiple gen ids are reported, placement uses the **first**. To place several
artifacts, queue several jobs.

## Placement (what Studio does on `done`)

| kind / target | lands as | route |
|---|---|---|
| `still` + `character:<k>` or `broll:<k>` | `stills/<k>.png` (+ stills sidecar stamp) | `POST /api/episodes/{slug}/still/{who}/import-generation` |
| `video` + `shot:<id>` | `clips/hf_<id>.mp4` (+ shot sidecar stamp, so the render reuses it) | `POST /api/episodes/{slug}/shot/{id}/import-generation` |
| `soul` | nothing downloaded — report `result_json={"soul_id":"..."}` | — |

Placement reuses the SSA-132 import-generation routes, so the same provenance
metadata (model, seed, resolution, raw/thumb URLs) is stamped on the imported
artifact. It is best-effort: if it fails (e.g. the episode moved), the job stays
`done` and the hook can re-run.

## REST surface (queue UI / Leo / debug — CoWork uses the MCP tools)

```
GET    /api/cowork/jobs?status=&episode=&kind=
GET    /api/cowork/jobs/stats?episode=
POST   /api/cowork/jobs                 # create (single or array)
POST   /api/cowork/jobs/claim           # {episode?, kinds?, by?}
POST   /api/cowork/jobs/clear           # {episode?}
GET    /api/cowork/jobs/{id}
PATCH  /api/cowork/jobs/{id}            # {status?, result_gen_ids?, note?, error?, result?}
DELETE /api/cowork/jobs/{id}
```

## Security

No per-tool auth — same trust model as the rest of Studio's MCP. The boundary is the
**LAN-only bind**. Do NOT tunnel `:8774/mcp` to untrusted networks.
