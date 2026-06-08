/* MACU Studio — demo Service Worker.
 *
 * This file is NOT part of the real Studio build. The demo (demo.mayorawesome.com)
 * serves Studio's UNMODIFIED production bundle; this SW, registered by a snippet
 * injected into index.html at demo-build time, is the entire "backend." It is
 * root-scoped, so it catches every same-origin /api/* request the app makes —
 * fetch(), EventSource(), and <video>/<img>/<iframe> src loads alike.
 *
 * Contract with build_demo.sh / gen_demo_fixtures.py:
 *   /data/api/<mirror of GET url path>.json   read-endpoint fixtures
 *   /data/media/...                            copied/transcoded binaries
 *   /data/media-map.json                       { "<api path, no query>": "media/<file>" }
 *
 * Everything that "does work" is simulated: POSTs return a fake job id, and the
 * matching SSE stream emits staged progress that lands on the pre-baked asset.
 * Writes (PUT) are echoed and kept in memory for the session only. Nothing here
 * ever reaches a real server.
 */
const DATA = "/data";
const JSON_HEADERS = { "Content-Type": "application/json", "Cache-Control": "no-store" };

let _mediaMap = null;
function mediaMap() {
  if (!_mediaMap) _mediaMap = fetch(`${DATA}/media-map.json`).then((r) => r.json()).catch(() => ({}));
  return _mediaMap;
}

// PUT edits kept for the session so a re-GET reflects them (refresh resets).
const sessionEdits = new Map();
let jobSeq = 0;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;        // 3rd-party (fonts) → network
  if (!url.pathname.startsWith("/api/")) return;          // app shell + /data/* → network
  event.respondWith(handle(event.request, url));
});

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: JSON_HEADERS });
}

async function handle(req, url) {
  const path = url.pathname;

  // ---- SSE streams (opened after a simulated job submit) ----
  if (/\/jobs\/[^/]+\/stream$/.test(path)) {
    return path.includes("/hf/jobs/") ? hfStream() : pipelineStream(path);
  }

  // ---- writes / job submits / AI-generate buttons ----
  if (req.method !== "GET") return mutate(req, path);

  // ---- binary media (audio / webp / mp4 / thumb), Range preserved ----
  const mm = await mediaMap();
  if (mm[path]) {
    const headers = {};
    const range = req.headers.get("Range");
    if (range) headers.Range = range;
    return fetch(`${DATA}/${mm[path]}`, { headers });  // nginx answers 206 on Range
  }

  // ---- session edit overrides a read of the same path ----
  if (sessionEdits.has(path)) return json(sessionEdits.get(path));

  // ---- HyperFrames template iframe preview — not meaningful in the demo ----
  if (path.includes("/hf/template-assets/")) {
    return new Response(
      "<!doctype html><body style='font:14px/1.5 monospace;color:#9aa;background:#111;padding:16px'>Template preview is disabled in the demo.</body>",
      { headers: { "Content-Type": "text/html" } });
  }

  // ---- static fixture, mirrored from the GET URL ----
  const fx = await fetch(`${DATA}/api${path.slice(4)}.json`);  // path starts with "/api"
  if (fx.ok) return new Response(fx.body, { status: 200, headers: JSON_HEADERS });

  // ---- benign defaults so an un-baked read never crashes the UI ----
  if (path.endsWith("/pipeline/active")) return json({ job_id: null });
  if (path.includes("/corpus/")) return json([]);
  if (path.includes("/versions/")) return json({ kind: "shot", key: "", canonical: "", current: { exists: false, mtime: null }, history: [], count: 0 });
  return json({});
}

function jobResp(id, hf = false) {
  return { job_id: id, queued: true,
    events_url: `/api/${hf ? "hf/" : ""}jobs/${id}/stream`,
    status_url: `/api/jobs/${id}/status` };
}

async function mutate(req, path) {
  if (req.method === "DELETE") return json({ ok: true });

  if (req.method === "PUT") {
    const body = await req.text();
    let parsed = null;
    try { parsed = JSON.parse(body); } catch { /* script PUT is raw markdown */ }
    if (path.endsWith("/script")) {
      sessionEdits.set(path, { text: body, mtime: Math.floor(Date.now() / 1000), exists: true });
    } else if (path.endsWith("/srt") && parsed?.entries) {
      sessionEdits.set(path, { text: "", entries: parsed.entries, exists: true });
    } else if (path.endsWith("/manifest") && parsed) {
      sessionEdits.set(path, parsed);
    }
    // permissive echo — superset of every PUT consumer's expected fields
    return json({ ok: true, mtime: Math.floor(Date.now() / 1000), bytes: body.length,
      count: parsed?.entries?.length ?? 0, path, speaker: "", mapped: true, propagated: true });
  }

  // POST ----------------------------------------------------------------
  // Job submitters → fake job id; the SSE stream below animates progress.
  if (/\/pipeline\/run$/.test(path) || /\/cue\/[^/]+\/regen$/.test(path) || /\/shot\/[^/]+\/regen$/.test(path)) {
    const kind = /\/pipeline\/run$/.test(path) ? "run" : "regen";
    return json(jobResp(`demo-${kind}-${++jobSeq}`));
  }
  if (/\/title\/[^/]+\/regen$/.test(path) || /\/ythumb\/regen$/.test(path) || /\/title\/new$/.test(path)) {
    return json(jobResp(`demo-hf-${++jobSeq}`, true));
  }

  // AI-generate / apply buttons → minimal valid empty results (no-op gracefully).
  if (path.endsWith("/shots/generate")) {
    return json({ characters: {}, broll: {}, cues: [], summary: { new_characters: [], reused_characters: [], new_broll: [], reused_broll: [], cues_planned: 0 } });
  }
  if (path.endsWith("/sfx/generate")) {
    return json({ sfx: [], summary: { opportunities: 0, reused: [], acquire: [] } });
  }
  if (path.endsWith("/manifest/from-script")) {
    return json({ summary: { old_cue_count: 0, new_cue_count: 0, cues_added: 0, cues_reshot: 0, changes: [], speakers: [], unmapped_speakers: [], segments: [], warnings: ["Demo mode — manifest generation is disabled."], renumbered: false } });
  }
  if (path.endsWith("/card-text/generate")) return json({ text: "", fields: {} });
  if (path.endsWith("/emergency-stop")) return json({ ok: true, report: { demo: "nothing to stop" } });
  if (path.endsWith("/git-sync")) return json({ ok: true, pushed: false, message: "Demo mode — no git." });
  if (path.endsWith("/diagnostics")) return json({ ok: true, checks: [] });

  return json({ ok: true });
}

// ---- synthetic SSE: 8-stage pipeline, or 1-stage for a single-cue/shot regen ----
function sse(steps, finalEvents) {
  const enc = new TextEncoder();
  const send = (ctrl, ev, obj) => ctrl.enqueue(enc.encode((ev ? `event: ${ev}\n` : "") + `data: ${JSON.stringify(obj)}\n\n`));
  const stream = new ReadableStream({
    start(ctrl) {
      let i = 0;
      const tick = () => {
        if (i < steps.length) { steps[i](ctrl, send); i++; setTimeout(tick, 380); }
        else { finalEvents(ctrl, send); ctrl.close(); }
      };
      send(ctrl, null, { ts: Date.now() / 1000, kind: "job.started", slug: "ep-005", from_stage: 1 });
      setTimeout(tick, 250);
    },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive" } });
}

function pipelineStream(path) {
  const full = /demo-run-/.test(path);
  const names = full
    ? ["Voice over", "Masters", "Frame interp", "Assemble", "Music", "Whisper", "Subtitles", "Burn"]
    : ["Render"];
  const steps = [];
  names.forEach((name, idx) => {
    const n = full ? idx + 1 : 8; // map single-stage regen onto the last cell
    steps.push((c, send) => send(c, null, { ts: Date.now() / 1000, kind: "stage.started", n, name }));
    steps.push((c, send) => send(c, null, { ts: Date.now() / 1000, kind: "stage.done", n, name, wall_s: 1 + idx }));
  });
  return sse(steps, (c, send) => {
    send(c, null, { ts: Date.now() / 1000, kind: "job.done", final: "ep-005.mp4" });
    send(c, "end", {});
  });
}

function hfStream() {
  const steps = [
    (c, send) => send(c, null, { kind: "log", line: "loading composition…" }),
    (c, send) => send(c, null, { kind: "log", line: "rendering frames…" }),
    (c, send) => send(c, null, { kind: "log", line: "encoding…" }),
  ];
  return sse(steps, (c, send) => {
    send(c, null, { kind: "job.done" });
    send(c, "end", {});
  });
}
