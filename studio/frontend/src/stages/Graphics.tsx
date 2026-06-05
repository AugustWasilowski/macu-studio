import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { graphicsApi } from "../api/graphics";
import { useStore } from "../store";
import { Badge, Dot } from "../components/Badge";
import { RegenNotes } from "../components/RegenNotes";
import { Modal } from "../components/Modal";
import { Field } from "../components/Field";
import { VersionArrows } from "../components/VersionArrows";
import { ThumbModal } from "../components/ThumbModal";
import { PlayBtn } from "../components/PlayBtn";
import { IRegen, IPlay, IPause, IX } from "../components/Icons";
import { useSfx, type PlayItem } from "./AudioSfx";
import { useCuePlayback } from "./useCuePlayback";
import { cueOffsets, coveredCues, makeOverlay } from "./overlayTiming";
import type { Overlay } from "../types";

interface HFEvent { ts: number; kind: string; n?: number; name?: string; line?: string; error?: string; [k: string]: unknown }

// Module-level drag payload for the title-card palette (same native-HTML5 idiom as AudioSfx).
let titleDrag: { asset: string } | null = null;

export function Graphics({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const busy = useStore((s) => s.busy);
  const setBusy = useStore((s) => s.setBusy);
  const selectedKey = useStore((s) => s.selectedTitleKey);
  const selectTitle = useStore((s) => s.selectTitle);

  const titles = useQuery({
    queryKey: ["titles", slug],
    queryFn: () => api.titles(slug),
    refetchInterval: 4000, // self-refresh so renders show up without navigating away
  });
  const cues = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug), refetchInterval: 4000 });
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });

  const [logLines, setLogLines] = useState<string[]>([]);

  const hfTemplates = useQuery({
    queryKey: ["hfTemplates"],
    queryFn: () => graphicsApi.templates(),
  });
  const templateOptions = hfTemplates.data?.templates ?? [];

  // ---- dope sheet: cue list + audio playback + overlay placements ----
  const cueList = cues.data?.cues ?? [];
  const overlays: Overlay[] = useMemo(
    () => ((manifest.data as any)?.overlays as Overlay[]) ?? [],
    [manifest.data],
  );
  const { cum } = useMemo(() => cueOffsets(cueList), [cueList]);

  const sfx = useSfx(slug);
  const playback = useCuePlayback({
    buildPlaylist: () => sfx.buildPlaylist(),
    resolveSingle: (cueId): PlayItem => {
      const c = cueList.find((x) => x.id === cueId);
      return { url: mediaUrl.cueAudio(slug, cueId, c?.wav_mtime), cueId, label: cueId };
    },
    notify: push,
  });
  const { continuous, setContinuous, curCueId, sequentialPlaying, togglePlay, playAll } = playback;

  const putOverlays = useMutation({
    mutationFn: (next: Overlay[]) => graphicsApi.putOverlays(slug, next),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }),
    onError: (e: Error) => push("overlays save failed: " + e.message, "err"),
  });
  const commitOverlays = (next: Overlay[]) => putOverlays.mutate(next);
  const addOverlay = (cueId: string, asset: string) => {
    const c = cueList.find((x) => x.id === cueId);
    commitOverlays([...overlays, makeOverlay(asset, cueId, c?.duration_s ?? 3)]);
    push(`${asset} → graphic on ${cueId}`, "ok");
  };
  const removeOverlay = (idx: number) => commitOverlays(overlays.filter((_, i) => i !== idx));
  const onDropCue = (cueId: string) => {
    if (!titleDrag) return;
    addOverlay(cueId, titleDrag.asset);
    titleDrag = null;
  };

  // overlays grouped by their anchor cue (rendered under that cue row)
  const overlaysByAnchor = useMemo(() => {
    const m = new Map<string, { ov: Overlay; idx: number }[]>();
    overlays.forEach((ov, idx) => {
      const k = ov.anchor_cue;
      (m.get(k) ?? m.set(k, []).get(k)!).push({ ov, idx });
    });
    return m;
  }, [overlays]);

  // ---- New title card modal ----
  const DEFAULT_FIELDS = '{\n  "kicker": "",\n  "title_line_1": "",\n  "title_line_2": "",\n  "sub": ""\n}';
  const [newOpen, setNewOpen] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newComp, setNewComp] = useState("");
  const [newFields, setNewFields] = useState(DEFAULT_FIELDS);
  // Card type drives the AI writer's brief (which composition + tone). Title-card modal
  // offers the non-thumbnail types; the thumbnail modal is always youtube_thumb.
  const [newCardType, setNewCardType] = useState("fresh_title");
  const cardTypes = useQuery({ queryKey: ["cardTypes"], queryFn: () => graphicsApi.cardTypes() });
  const titleCardTypes = (cardTypes.data?.card_types ?? ["macu_title", "fresh_title", "weather"])
    .filter((t) => t !== "youtube_thumb");
  useEffect(() => {
    if (!newComp && templateOptions.length) setNewComp(templateOptions[0]);
  }, [templateOptions, newComp]);
  const openNewFor = (key: string) => {
    setNewKey(key);
    setNewComp((c) => c || templateOptions[0] || "");
    setNewFields(DEFAULT_FIELDS);
    setNewOpen(true);
  };

  // ---- YouTube thumbnail ----
  const [thumbOpen, setThumbOpen] = useState(false);
  const [thumbFields, setThumbFields] = useState('{\n  "title_line_1": "",\n  "title_line_2": ""\n}');
  const [thumbOverride, setThumbOverride] = useState<string | null>(null);
  const [thumbBust, setThumbBust] = useState(0);
  const [thumbViewOpen, setThumbViewOpen] = useState(false);

  function watchHfJob(jobId: string, key: string) {
    const es = new EventSource(`/api/hf/jobs/${jobId}/stream`);
    setBusy(`title:${key}`, true);
    es.onmessage = (m) => {
      let ev: HFEvent;
      try { ev = JSON.parse(m.data); } catch { return; }
      if (ev.kind === "log" && typeof ev.line === "string") {
        setLogLines((L) => [...L.slice(-200), `[${key}] ${ev.line}`]);
      } else if (ev.kind === "job.done") {
        setBusy(`title:${key}`, false);
        push(`title ${key} rendered`, "ok");
        qc.invalidateQueries({ queryKey: ["titles", slug] });
        es.close();
      } else if (ev.kind === "job.error" || ev.kind === "stage.error") {
        setBusy(`title:${key}`, false);
        push(`title ${key} failed: ${ev.error}`, "err");
        setLogLines((L) => [...L.slice(-200), `[${key}] ERROR: ${ev.error}`]);
        es.close();
      }
    };
    es.addEventListener("end", () => es.close());
  }

  const regen = useMutation({
    mutationFn: (key: string) => fetch(`/api/episodes/${slug}/title/${key}/regen`, { method: "POST" }).then(async (r) => {
      const text = await r.text();
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${text}`);
      return JSON.parse(text);
    }),
    onMutate: (key) => { setBusy(`title:${key}`, true); push(`title ${key} → HyperFrames`, "run"); },
    onError: (e: Error, key) => {
      setBusy(`title:${key}`, false);
      push(`title ${key}: ${e.message}`, "err");
    },
    onSuccess: (r, key) => {
      if (r.job_id) watchHfJob(r.job_id, key);
    },
  });

  const newTitle = useMutation({
    mutationFn: (args: { key: string; composition: string; fields: Record<string, unknown> }) =>
      graphicsApi.newTitle(slug, args),
    onMutate: (a) => { setBusy(`title:${a.key}`, true); push(`new title ${a.key} → HyperFrames`, "run"); },
    onError: (e: Error, a) => {
      setBusy(`title:${a.key}`, false);
      push(`new title ${a.key}: ${e.message}`, "err");
    },
    onSuccess: (r, a) => {
      setNewOpen(false);
      qc.invalidateQueries({ queryKey: ["titles", slug] });
      if (r.job_id) watchHfJob(r.job_id, a.key);
    },
  });

  const regenThumb = useMutation({
    mutationFn: (fields: Record<string, unknown>) =>
      graphicsApi.regenYThumb(slug, { fields }),
    onMutate: () => { setBusy("ythumb", true); push("thumbnail → HyperFrames", "run"); },
    onError: (e: Error) => {
      setBusy("ythumb", false);
      push(`thumbnail: ${e.message}`, "err");
    },
    onSuccess: (r) => {
      setThumbOpen(false);
      if (r.job_id) {
        const es = new EventSource(`/api/hf/jobs/${r.job_id}/stream`);
        es.onmessage = (m) => {
          let ev: HFEvent;
          try { ev = JSON.parse(m.data); } catch { return; }
          if (ev.kind === "log" && typeof ev.line === "string") {
            setLogLines((L) => [...L.slice(-200), `[thumb] ${ev.line}`]);
          } else if (ev.kind === "job.done") {
            setBusy("ythumb", false);
            push("thumbnail rendered", "ok");
            setThumbOverride(null);
            setThumbBust((n) => n + 1);
            qc.invalidateQueries({ queryKey: ["versions", "ythumb", slug, slug] });
            es.close();
          } else if (ev.kind === "job.error" || ev.kind === "stage.error") {
            setBusy("ythumb", false);
            push(`thumbnail failed: ${ev.error}`, "err");
            setLogLines((L) => [...L.slice(-200), `[thumb] ERROR: ${ev.error}`]);
            es.close();
          }
        };
        es.addEventListener("end", () => es.close());
      }
    },
  });

  // AI card-text writer (on-demand Ollama). Fills the fields textarea in either modal.
  const genText = useMutation({
    mutationFn: (args: { card_type: string; target: "title" | "thumb" }) =>
      graphicsApi.genCardText(slug, { card_type: args.card_type }),
    onMutate: (a) => push(`writing ${a.card_type.replace("_", " ")} text…`, "run"),
    onError: (e: Error) => push(`card text: ${e.message}`, "err"),
    onSuccess: (r, a) => {
      const pretty = JSON.stringify(r.fields, null, 2);
      if (a.target === "thumb") {
        setThumbFields(pretty);
      } else {
        setNewFields(pretty);
        if (r.composition) setNewComp(r.composition);
      }
      (r.warnings ?? []).forEach((w) => push(w, "info"));
      push("card text written — review + edit before render", "ok");
    },
  });

  function submitNewTitle() {
    let fields: Record<string, unknown> = {};
    try { fields = JSON.parse(newFields || "{}"); }
    catch { push("fields must be valid JSON", "err"); return; }
    if (!newKey.trim()) { push("key required", "err"); return; }
    if (!newComp) { push("composition required", "err"); return; }
    newTitle.mutate({ key: newKey.trim(), composition: newComp, fields });
  }

  function submitRegenThumb() {
    let fields: Record<string, unknown> = {};
    try { fields = JSON.parse(thumbFields || "{}"); }
    catch { push("fields must be valid JSON", "err"); return; }
    regenThumb.mutate(fields);
  }

  const renderAllMissing = () => {
    const ts = (titles.data?.titles ?? []).filter(
      (t) => t.configured && (t.status === "missing" || t.status === "stale")
    );
    if (!ts.length) { push("No missing or stale titles", "info"); return; }
    push(`Queuing ${ts.length} title renders`, "run");
    ts.forEach((t, i) => setTimeout(() => regen.mutate(t.key), i * 300));
  };

  const list = titles.data?.titles ?? [];
  const cards = list.filter((t) => t.scope !== "hyperframes");
  const hfStrip = list.filter((t) => t.scope === "hyperframes");
  const renderedCount = cards.filter((c) => c.status === "rendered" || c.status === "shared").length;

  const cur = useMemo(
    () => cards.find((t) => t.key === selectedKey) ?? cards[0],
    [cards, selectedKey],
  );
  useEffect(() => {
    if (!selectedKey && cards.length) selectTitle(cards[0].key);
  }, [cards, selectedKey, selectTitle]);

  return (
    <div className="grid grid-cols-[1fr_380px] gap-3 h-full min-h-0">
      {/* LEFT — the dope sheet: cue list + audio playback + drop-to-place graphics */}
      <section className="panel flex flex-col min-h-0">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">DOPE SHEET <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ drag a card onto a cue · set the span on Video ▸ Timeline</span></div>
          <div className="flex items-center gap-2">
            <span className="seg-readout">{overlays.length} GFX</span>
            <button className="btn btn-cyan" onClick={playAll} title={sequentialPlaying ? "Stop playback" : "Play VO + SFX in sequence"}>
              {sequentialPlaying ? <IPause /> : <IPlay />} {sequentialPlaying ? "Stop" : "Play all"}
            </button>
            <label className="flex items-center gap-1 text-[11px] text-txt-dim cursor-pointer select-none" title="Row play continues to the next clip (off = one clip only)">
              <input type="checkbox" checked={continuous} onChange={(e) => setContinuous(e.target.checked)} />
              Continuous
            </label>
          </div>
        </header>
        <div className="overflow-y-auto flex-1">
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-bg-1">
              <tr className="label-tiny text-left border-b hairline-soft">
                <th className="px-2 py-1">CUE</th>
                <th className="px-2 py-1">SPEAKER</th>
                <th className="px-2 py-1">VO TEXT</th>
                <th className="px-2 py-1">DUR</th>
                <th className="px-2 py-1"></th>
              </tr>
            </thead>
            <tbody>
              {cueList.map((c) => {
                const isPlaying = curCueId === c.id;
                const anchored = overlaysByAnchor.get(c.id) ?? [];
                return (
                  <CueRow
                    key={c.id}
                    slug={slug}
                    cueId={c.id}
                    speaker={c.speaker}
                    text={c.is_hold ? `[HOLD ${c.hold_seconds}s]` : c.text}
                    durationS={c.duration_s}
                    wavExists={c.wav_exists}
                    isPlaying={isPlaying}
                    onPlay={() => togglePlay(c.id)}
                    onDropCard={() => onDropCue(c.id)}
                    anchored={anchored}
                    cueList={cueList}
                    cum={cum}
                    onRemoveOverlay={removeOverlay}
                  />
                );
              })}
            </tbody>
          </table>
          {cueList.length === 0 && <div className="p-4 text-txt-faint">No cues in manifest yet.</div>}
        </div>
        {logLines.length > 0 && (
          <div className="border-t hairline-soft">
            <div className="px-3 py-1 flex items-center justify-between">
              <span className="label-tiny">render log tail</span>
              <button className="btn p-0.5 text-[11px]" onClick={() => setLogLines([])}>clear</button>
            </div>
            <pre className="logtail mx-3 mb-3" style={{ height: 120 }}>{logLines.join("\n")}</pre>
          </div>
        )}
      </section>

      {/* RIGHT — title-card palette (draggable) + preview + YouTube thumbnail */}
      <aside className="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <section className="panel flex flex-col">
          <header className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">TITLE CARDS <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ drag → a cue</span></div>
            <span className="seg-readout">{renderedCount}<span className="text-txt-faint">/{cards.length}</span></span>
          </header>
          <div className="p-2 grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
            {cards.map((t) => {
              const active = selectedKey === t.key;
              const isBusy = !!busy[`title:${t.key}`];
              return (
                <div
                  key={t.key}
                  draggable
                  onDragStart={() => { titleDrag = { asset: t.key }; }}
                  onClick={() => selectTitle(t.key)}
                  title="drag onto a cue to place · click to preview"
                  className={"hairline-soft text-left p-0 overflow-hidden rounded transition-colors cursor-grab " + (active ? "border-amber" : "")}
                  style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)" } : {}}
                >
                  <div className="bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
                    {t.exists ? (
                      <video
                        key={mediaUrl.titlePreview(slug, t.key) + (t.mtime ?? "")}
                        src={mediaUrl.titlePreview(slug, t.key)}
                        autoPlay muted loop playsInline
                        className="w-full h-full object-contain pointer-events-none"
                      />
                    ) : (
                      <div className="text-center">
                        <Badge status={isBusy ? "running" : t.status} />
                        <div className="label-tiny mt-1">
                          {t.scope === "shared"
                            ? (t.status === "missing" ? "shared — not found" : "shared")
                            : `${t.key}.mp4`}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-between px-2 py-1 bg-bg-2">
                    <span className="font-mono text-[11px] truncate" title={t.key}>{t.key}</span>
                    <span onClick={(e) => e.stopPropagation()} className="flex items-center gap-1">
                      <button
                        className="btn p-1"
                        title={t.configured ? "Regen via HyperFrames" : "Configure + generate"}
                        disabled={isBusy}
                        onClick={() => (t.configured ? regen.mutate(t.key) : openNewFor(t.key))}
                      ><IRegen /></button>
                    </span>
                  </div>
                </div>
              );
            })}
            {cards.length === 0 && (
              <div className="text-txt-faint col-span-full p-2 text-[12px]">No title_assets in manifest.</div>
            )}
          </div>
          <div className="px-3 py-2 border-t hairline-soft flex items-center gap-2">
            <button className="btn btn-cyan" onClick={() => setNewOpen(true)}>+ New title card</button>
            <button className="btn btn-amber" onClick={renderAllMissing}><IRegen /> Render missing</button>
          </div>
          {hfStrip.length > 0 && (
            <div className="px-3 py-2 border-t hairline-soft flex items-center gap-2 flex-wrap">
              <span className="label-tiny">hyperframes/</span>
              {hfStrip.map((h) => (
                <span key={h.key} className="hairline-soft px-2 py-0.5 inline-flex items-center gap-1.5 rounded">
                  <Dot status={h.status} />
                  <span className="font-mono text-[11px]">{h.key}.html</span>
                </span>
              ))}
            </div>
          )}
        </section>

        <section className="panel p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="panel-title">PREVIEW</div>
            {cur && <Badge status={cur.status} />}
          </div>
          {cur ? (
            <>
              {cur.exists ? (
                <video
                  key={mediaUrl.titlePreview(slug, cur.key) + (cur.mtime ?? "")}
                  src={mediaUrl.titlePreview(slug, cur.key)}
                  autoPlay muted loop playsInline controls
                  className="w-full bg-black hairline-soft rounded"
                  style={{ aspectRatio: "1/1" }}
                />
              ) : (
                <div className="hairline-soft bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
                  <div className="text-center">
                    <Badge status={cur.status} />
                    <div className="label-tiny mt-2 break-all">
                      {cur.scope === "shared"
                        ? "shared assets/titles/ — file not found"
                        : `episodes/${slug}/titles/${cur.key}.mp4 (not built)`}
                    </div>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-1 text-[12px]">
                <span className="label-tiny">key</span><span className="font-mono">{cur.key}</span>
                <span className="label-tiny">scope</span><span>{cur.scope}</span>
                <span className="label-tiny">status</span><span>{cur.status}</span>
              </div>
              <div className="flex items-center gap-2">
                {cur.configured ? (
                  <button className="btn btn-cyan" disabled={!!busy[`title:${cur.key}`]} onClick={() => regen.mutate(cur.key)}>
                    <IRegen /> Regen
                  </button>
                ) : (
                  <button className="btn btn-cyan" onClick={() => openNewFor(cur.key)}>
                    <IRegen /> Configure + generate
                  </button>
                )}
                {cur.configured && <RegenNotes onSubmit={() => regen.mutate(cur.key)} />}
              </div>
            </>
          ) : (
            <div className="text-txt-faint">No title selected.</div>
          )}
        </section>

        <section className="panel">
          <div className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">YOUTUBE THUMBNAIL</div>
            <button className="btn btn-cyan" disabled={!!busy.ythumb} onClick={() => setThumbOpen(true)}><IRegen /> Regenerate</button>
          </div>
          <div className="p-3 flex flex-col gap-2">
            <button
              className="bg-black hairline-soft rounded overflow-hidden grid place-items-center cursor-zoom-in p-0"
              style={{ aspectRatio: "16/9" }}
              title="Click to enlarge · browse versions · see the template + fields"
              onClick={() => setThumbViewOpen(true)}
            >
              <img
                key={(thumbOverride ?? graphicsApi.ythumbPreviewUrl(slug)) + `?b=${thumbBust}`}
                src={thumbOverride ?? `${graphicsApi.ythumbPreviewUrl(slug)}?b=${thumbBust}`}
                alt="youtube thumbnail"
                className="w-full h-full object-contain"
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
                onLoad={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "visible"; }}
              />
            </button>
            <VersionArrows
              slug={slug}
              kind="ythumb"
              vkey={slug}
              onView={(u) => setThumbOverride(u)}
              onChanged={() => { setThumbOverride(null); setThumbBust((n) => n + 1); }}
            />
          </div>
        </section>
      </aside>

      <Modal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        title="New title card"
        footer={
          <>
            <button className="btn" onClick={() => setNewOpen(false)}>Cancel</button>
            <button className="btn btn-cyan" disabled={newTitle.isPending} onClick={submitNewTitle}>Create + render</button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <Field label="key" value={newKey} onChange={setNewKey} placeholder="e.g. lower_third" monospace />
          <Field
            label="composition"
            value={newComp}
            onChange={setNewComp}
            options={templateOptions.length ? templateOptions : [""]}
          />
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field label="AI card type" value={newCardType} onChange={setNewCardType} options={titleCardTypes} />
            </div>
            <button
              className="btn btn-amber whitespace-nowrap"
              disabled={genText.isPending}
              title="Write deadpan card text with the local LLM (Ollama) from this episode's script"
              onClick={() => genText.mutate({ card_type: newCardType, target: "title" })}
            >✨ {genText.isPending ? "Writing…" : "Write with AI"}</button>
          </div>
          <Field label="fields (JSON)" value={newFields} onChange={setNewFields} rows={6} monospace />
        </div>
      </Modal>

      <Modal
        open={thumbOpen}
        onClose={() => setThumbOpen(false)}
        title="Regenerate YouTube thumbnail"
        footer={
          <>
            <button className="btn" onClick={() => setThumbOpen(false)}>Cancel</button>
            <button className="btn btn-cyan" disabled={regenThumb.isPending} onClick={submitRegenThumb}>Regenerate</button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-txt-dim text-[12px]">
            Renders the <code>youtube_thumb</code> composition to{" "}
            <code>final/{slug}_thumb.png</code>. The current thumbnail is archived first.
          </p>
          <div className="flex justify-end">
            <button
              className="btn btn-amber"
              disabled={genText.isPending}
              title="Write a punchy deadpan thumbnail hook with the local LLM (Ollama)"
              onClick={() => genText.mutate({ card_type: "youtube_thumb", target: "thumb" })}
            >✨ {genText.isPending ? "Writing…" : "Write with AI"}</button>
          </div>
          <Field label="fields (JSON)" value={thumbFields} onChange={setThumbFields} rows={6} monospace />
        </div>
      </Modal>

      <ThumbModal
        open={thumbViewOpen}
        onClose={() => setThumbViewOpen(false)}
        slug={slug}
        liveParams={((manifest.data as any)?.youtube_thumb as { composition?: string; fields?: Record<string, unknown> }) ?? null}
        livePreviewUrl={`${graphicsApi.ythumbPreviewUrl(slug)}?b=${thumbBust}`}
        onChanged={() => { setThumbOverride(null); setThumbBust((n) => n + 1); qc.invalidateQueries({ queryKey: ["manifest", slug] }); }}
      />
    </div>
  );
}

/* One dope-sheet row: the cue + a drop target + any graphics anchored to it. */
function CueRow({
  slug, cueId, speaker, text, durationS, wavExists, isPlaying,
  onPlay, onDropCard, anchored, cueList, cum, onRemoveOverlay,
}: {
  slug: string;
  cueId: string;
  speaker: string;
  text: string;
  durationS: number | null;
  wavExists: boolean;
  isPlaying: boolean;
  onPlay: () => void;
  onDropCard: () => void;
  anchored: { ov: Overlay; idx: number }[];
  cueList: { id: string; duration_s: number | null }[];
  cum: Record<string, number>;
  onRemoveOverlay: (idx: number) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <>
      <tr
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={() => { setOver(false); onDropCard(); }}
        className={"border-b border-[var(--line-soft)] hover:bg-bg-3 " + (over ? "outline outline-1 outline-[var(--cyan)] bg-bg-3" : "")}
      >
        <td className="px-2 py-1.5 text-amber font-bold">{cueId}</td>
        <td className="px-2 py-1.5 whitespace-nowrap">{speaker}</td>
        <td className="px-2 py-1.5 max-w-[360px] truncate" title={text}>{text}</td>
        <td className="px-2 py-1.5 text-cyan whitespace-nowrap">{durationS != null ? `${durationS.toFixed(1)}s` : "—"}</td>
        <td className="px-2 py-1.5">
          <PlayBtn playing={isPlaying} onClick={onPlay} title={wavExists ? "Play" : "No wav yet"} />
        </td>
      </tr>
      {anchored.length > 0 && (
        <tr>
          <td colSpan={5} className="p-0">
            <div className="pl-9 pr-2 pb-1 flex flex-col gap-1">
              {anchored.map(({ ov, idx }) => {
                const span = coveredCues(ov, cueList, cum);
                const spanLabel = span.length <= 1 ? (span[0] ?? cueId) : `${span[0]}–${span[span.length - 1]}`;
                return (
                  <div key={ov.id ?? idx} className="flex items-center gap-2 text-[11px] hairline-soft rounded px-2 py-0.5 bg-bg-2">
                    <span className="text-cyan">▦</span>
                    <video
                      src={mediaUrl.titlePreview(slug, ov.asset)}
                      muted loop autoPlay playsInline
                      className="bg-black rounded pointer-events-none"
                      style={{ width: 28, height: 28, objectFit: "contain" }}
                    />
                    <span className="font-mono flex-1 truncate" title={ov.asset}>{ov.asset}</span>
                    <span className={"px-1 rounded text-[10px] " + (ov.mode === "overlay" ? "text-cyan" : "text-amber")}>{ov.mode}</span>
                    <span className="text-txt-faint">{spanLabel} · {(ov.duration ?? 0).toFixed(1)}s</span>
                    <button className="btn p-0.5" title="remove graphic" onClick={() => onRemoveOverlay(idx)}><IX /></button>
                  </div>
                );
              })}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
