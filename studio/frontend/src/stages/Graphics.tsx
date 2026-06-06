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
import { IRegen } from "../components/Icons";

interface HFEvent { ts: number; kind: string; n?: number; name?: string; line?: string; error?: string; [k: string]: unknown }

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
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });

  const [logLines, setLogLines] = useState<string[]>([]);

  const hfTemplates = useQuery({
    queryKey: ["hfTemplates"],
    queryFn: () => graphicsApi.templates(),
  });
  const templateOptions = hfTemplates.data?.templates ?? [];

  // ---- New title card modal ----
  const DEFAULT_FIELDS = '{\n  "kicker": "",\n  "title_line_1": "",\n  "title_line_2": "",\n  "sub": ""\n}';
  const [newOpen, setNewOpen] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newComp, setNewComp] = useState("");
  const [newFields, setNewFields] = useState(DEFAULT_FIELDS);
  const [editMode, setEditMode] = useState(false);     // editing an existing object-form card
  const [legacyNote, setLegacyNote] = useState("");    // descriptive string for bespoke/legacy cards
  const [newBrief, setNewBrief] = useState("");        // brief for AI composition generation
  // Card type drives the AI writer's brief (which composition + tone). Title-card modal
  // offers the non-thumbnail types; the thumbnail modal is always youtube_thumb.
  const [newCardType, setNewCardType] = useState("fresh_title");
  const cardTypes = useQuery({ queryKey: ["cardTypes"], queryFn: () => graphicsApi.cardTypes() });
  const titleCardTypes = (cardTypes.data?.card_types ?? ["macu_title", "fresh_title", "weather"])
    .filter((t) => t !== "youtube_thumb");
  useEffect(() => {
    if (!newComp && templateOptions.length) setNewComp(templateOptions[0]);
  }, [templateOptions, newComp]);
  // Open the modal for an existing card. If its manifest entry is the object form
  // ({composition, fields}) we're EDITING — pre-fill both. If it's a bespoke/legacy
  // string entry there are no saved fields to load, so fall back to configure mode and
  // surface the descriptive string as a hint.
  const openNewFor = (key: string) => {
    const ta = ((manifest.data as any)?.title_assets ?? {})[key];
    setNewKey(key); setNewBrief("");
    if (ta && typeof ta === "object") {
      setEditMode(true);
      setNewComp(ta.composition || templateOptions[0] || "");
      setNewFields(JSON.stringify(ta.fields ?? {}, null, 2));
      setLegacyNote("");
    } else {
      setEditMode(false);
      setNewComp((c) => c || templateOptions[0] || "");
      setNewFields(DEFAULT_FIELDS);
      setLegacyNote(typeof ta === "string" ? ta : "");
    }
    setNewOpen(true);
  };

  const openNew = () => {
    setEditMode(false); setNewKey(""); setLegacyNote(""); setNewBrief("");
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

  // On-demand Ollama: generate a whole NEW HyperFrames composition (animated card) from a
  // brief. Saves it as the template named by `key`, then selects it + loads its placeholder
  // fields so you can fill values and Create + render.
  const genComp = useMutation({
    mutationFn: (args: { key: string; brief: string }) => graphicsApi.genComposition(slug, args),
    onMutate: () => push("generating composition (local Qwen) — ~30-60s…", "run"),
    onError: (e: Error) => push(`composition: ${e.message}`, "err"),
    onSuccess: (r) => {
      setNewComp(r.composition);
      setNewFields(JSON.stringify(r.fields ?? {}, null, 2));
      qc.invalidateQueries({ queryKey: ["hfTemplates"] });
      qc.invalidateQueries({ queryKey: ["titles", slug] });   // card now exists → show it in the grid
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      selectTitle(r.composition);
      push(`card "${r.composition}" created (${r.placeholders.length} fields) — fill the values, then Create + render`, "ok");
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
    <div className="grid grid-cols-[minmax(0,1fr)_380px] grid-rows-[minmax(0,1fr)] gap-3 h-full min-h-0">
      {/* LEFT — large preview of the selected title card + metadata underneath */}
      <section className="panel flex flex-col min-h-0 p-3 gap-3">
        <div className="flex items-center justify-between flex-none">
          <div className="panel-title">PREVIEW <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {cur ? cur.key : "select a card →"}</span></div>
          {cur && <Badge status={cur.status} />}
        </div>
        {cur ? (
          <>
            <div className="flex-1 min-h-0 bg-black hairline-soft rounded grid place-items-center overflow-hidden">
              {cur.exists ? (
                <video
                  key={mediaUrl.titlePreview(slug, cur.key) + (cur.mtime ?? "")}
                  src={mediaUrl.titlePreview(slug, cur.key)}
                  autoPlay muted loop playsInline controls
                  className="max-h-full max-w-full object-contain"
                />
              ) : (
                <div className="text-center">
                  <Badge status={cur.status} />
                  <div className="label-tiny mt-2 break-all px-4">
                    {cur.scope === "shared"
                      ? "shared assets/titles/ — file not found"
                      : `episodes/${slug}/titles/${cur.key}.mp4 (not built)`}
                  </div>
                </div>
              )}
            </div>
            <div className="grid grid-cols-[80px_1fr] gap-x-2 gap-y-1 text-[12px] flex-none">
              <span className="label-tiny">key</span><span className="font-mono">{cur.key}</span>
              <span className="label-tiny">scope</span><span>{cur.scope}</span>
              <span className="label-tiny">status</span><span>{cur.status}</span>
            </div>
            <div className="flex items-center gap-2 flex-none">
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
          <div className="flex-1 grid place-items-center text-txt-faint">No title selected — pick one from the cards on the right.</div>
        )}
      </section>

      {/* RIGHT — title-card palette (click → preview on the left) + YouTube thumbnail */}
      <aside className="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <section className="panel flex flex-col">
          <header className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">TITLE CARDS <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ click → preview</span></div>
            <span className="seg-readout">{renderedCount}<span className="text-txt-faint">/{cards.length}</span></span>
          </header>
          <div className="p-2 grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(104px, 1fr))" }}>
            {cards.map((t) => {
              const active = selectedKey === t.key;
              const isBusy = !!busy[`title:${t.key}`];
              return (
                <div
                  key={t.key}
                  onClick={() => selectTitle(t.key)}
                  title="click to preview"
                  className={"hairline-soft text-left p-0 overflow-hidden rounded transition-colors cursor-pointer " + (active ? "border-amber" : "")}
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
            <button className="btn btn-cyan" onClick={openNew}>+ New title card</button>
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

        {logLines.length > 0 && (
          <section className="panel">
            <div className="px-3 py-1 flex items-center justify-between border-b hairline-soft">
              <span className="label-tiny">render log tail</span>
              <button className="btn p-0.5 text-[11px]" onClick={() => setLogLines([])}>clear</button>
            </div>
            <pre className="logtail mx-3 my-3" style={{ height: 120 }}>{logLines.join("\n")}</pre>
          </section>
        )}
      </aside>

      <Modal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        title={editMode ? "Edit title card" : "New title card"}
        footer={
          <>
            <button className="btn" onClick={() => setNewOpen(false)}>Cancel</button>
            <button className="btn btn-cyan" disabled={newTitle.isPending} onClick={submitNewTitle}>{editMode ? "Save + render" : "Create + render"}</button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {editMode ? (
            <div className="flex items-center gap-2 text-[12px]"><span className="label-tiny">key</span><span className="font-mono text-amber">{newKey}</span></div>
          ) : (
            <Field label="key" value={newKey} onChange={setNewKey} placeholder="e.g. lower_third" monospace />
          )}
          {legacyNote && (
            <div className="hairline-soft rounded p-2 text-[11px] text-txt-dim">
              <span className="label-tiny text-amber">no saved fields</span> — this card was authored as a description, not from a composition. Pick a composition + fill the fields to configure it (or keep generating it from a prompt).
              <div className="mt-1 font-mono text-txt-faint break-words">{legacyNote}</div>
            </div>
          )}
          <Field
            label="composition"
            value={newComp}
            onChange={setNewComp}
            options={Array.from(new Set([newComp, ...templateOptions].filter(Boolean))) as string[]}
          />
          {/* Generate a whole NEW composition (animated card HTML) from a brief, via local Qwen.
              Needs a key (used as the new composition's name). */}
          <div className="hairline-soft rounded p-2 flex flex-col gap-2">
            <div className="label-tiny">generate a new composition with AI <span className="text-txt-faint normal-case tracking-normal">(local Qwen → HyperFrames HTML)</span></div>
            <Field label="brief" value={newBrief} onChange={setNewBrief} rows={3}
              placeholder="e.g. a Crater Bowl scoreboard: SECTOR NINE SLAGS vs SECTOR FOUR GLOWBOYS, score ticks 2 → 1, ‘PLAYERS REMAINING’ underneath" />
            <button
              className="btn btn-amber self-start"
              disabled={genComp.isPending || !newKey.trim() || !newBrief.trim()}
              title="Generate a brand-new HyperFrames composition from this brief (saved as the composition named by the key above)"
              onClick={() => genComp.mutate({ key: newKey.trim(), brief: newBrief })}
            >✨ {genComp.isPending ? "Generating…" : "Generate composition"}</button>
          </div>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <Field label="AI card type" value={newCardType} onChange={setNewCardType} options={titleCardTypes} />
            </div>
            <button
              className="btn btn-amber whitespace-nowrap"
              disabled={genText.isPending}
              title="Write deadpan card text (the five fields) with the local LLM from this episode's script"
              onClick={() => genText.mutate({ card_type: newCardType, target: "title" })}
            >✨ {genText.isPending ? "Writing…" : "Write fields with AI"}</button>
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
