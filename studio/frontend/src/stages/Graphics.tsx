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
import { useT } from "../i18n";

interface HFEvent { ts: number; kind: string; n?: number; name?: string; line?: string; error?: string; [k: string]: unknown }

// One-liners for the AI card types (mirror backend cardgen.CARD_TYPES). These are card
// ARCHETYPES, not just tone — each pins a composition the AI writer snaps to.
const CARD_TYPE_BLURB_KEY: Record<string, string> = {
  macu_title: "graphics.cardBlurb.macuTitle",
  fresh_title: "graphics.cardBlurb.freshTitle",
  weather: "graphics.cardBlurb.weather",
};

export function Graphics({ slug }: { slug: string }) {
  const t = useT();
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
  const [compGenerated, setCompGenerated] = useState(false); // brief has been turned into a composition
  // Card type drives the AI writer's brief (which composition + tone). Title-card modal
  // offers the non-thumbnail types; the thumbnail modal is always youtube_thumb.
  const [newCardType, setNewCardType] = useState("fresh_title");
  const cardTypes = useQuery({ queryKey: ["cardTypes"], queryFn: () => graphicsApi.cardTypes() });
  const titleCardTypes = (cardTypes.data?.card_types ?? ["macu_title", "fresh_title", "weather"])
    .filter((ct) => ct !== "youtube_thumb");
  useEffect(() => {
    if (!newComp && templateOptions.length) setNewComp(templateOptions[0]);
  }, [templateOptions, newComp]);

  // Scaffold the fields JSON from a composition's actual ‹PLACEHOLDER› tokens, so you can
  // see what to fill without writing-with-AI. Preserves any values for keys that still
  // exist (`preserveJson`), fills new keys empty, drops keys the layout no longer has.
  // No-op if the template is unknown / has no placeholders (leaves the JSON untouched).
  const fillFieldsFor = async (comp: string, preserveJson: string) => {
    if (!comp) return;
    try {
      const r = await graphicsApi.templateFields(comp);
      if (!Object.keys(r.fields).length) return;
      let existing: Record<string, unknown> = {};
      try { existing = JSON.parse(preserveJson || "{}"); } catch { /* keep empty */ }
      const merged: Record<string, unknown> = {};
      for (const k of Object.keys(r.fields)) merged[k] = k in existing ? existing[k] : r.fields[k];
      setNewFields(JSON.stringify(merged, null, 2));
    } catch { /* leave fields as-is */ }
  };

  // Picking a layout reshapes the JSON to match it (carrying over overlapping values).
  const onPickComposition = (comp: string) => {
    setNewComp(comp);
    fillFieldsFor(comp, newFields);
  };

  // Open the modal for an existing card. If its manifest entry is the object form
  // ({composition, fields}) we're EDITING — pre-fill both. If it's a bespoke/legacy
  // string entry there are no saved fields to load, so fall back to configure mode and
  // surface the descriptive string as a hint. Either way we scaffold the fields from the
  // composition's placeholders (merging saved values in) so the JSON is never blank.
  const openNewFor = (key: string) => {
    const ta = ((manifest.data as any)?.title_assets ?? {})[key];
    setNewKey(key); setNewBrief(""); setCompGenerated(false);
    if (ta && typeof ta === "object") {
      setEditMode(true);
      const comp = ta.composition || templateOptions[0] || "";
      const saved = JSON.stringify(ta.fields ?? {}, null, 2);
      setNewComp(comp);
      setNewFields(saved);
      setLegacyNote("");
      fillFieldsFor(comp, saved);
    } else {
      setEditMode(false);
      const comp = newComp || templateOptions[0] || "";
      setNewComp(comp);
      setNewFields(DEFAULT_FIELDS);
      setLegacyNote(typeof ta === "string" ? ta : "");
      fillFieldsFor(comp, "{}");
    }
    setNewOpen(true);
  };

  const openNew = () => {
    setEditMode(false); setNewKey(""); setLegacyNote(""); setNewBrief(""); setCompGenerated(false);
    const comp = newComp || templateOptions[0] || "";
    setNewComp(comp);
    setNewFields(DEFAULT_FIELDS);
    fillFieldsFor(comp, "{}");
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
        push(t("toast.titleRendered", { key }), "ok");
        qc.invalidateQueries({ queryKey: ["titles", slug] });
        es.close();
      } else if (ev.kind === "job.error" || ev.kind === "stage.error") {
        setBusy(`title:${key}`, false);
        push(t("toast.titleFailed", { key, error: ev.error }), "err");
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
    onMutate: (key) => { setBusy(`title:${key}`, true); push(t("toast.titleQueued", { key }), "run"); },
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
    onMutate: (a) => { setBusy(`title:${a.key}`, true); push(t("toast.newTitleQueued", { key: a.key }), "run"); },
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
    onMutate: () => { setBusy("ythumb", true); push(t("toast.thumbQueued"), "run"); },
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
            push(t("toast.thumbRendered"), "ok");
            setThumbOverride(null);
            setThumbBust((n) => n + 1);
            qc.invalidateQueries({ queryKey: ["versions", "ythumb", slug, slug] });
            es.close();
          } else if (ev.kind === "job.error" || ev.kind === "stage.error") {
            setBusy("ythumb", false);
            push(t("toast.thumbFailed", { error: ev.error }), "err");
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
      push(t("toast.cardTextWritten"), "ok");
    },
  });

  // On-demand Ollama: generate a whole NEW HyperFrames composition (animated card) from a
  // brief. Saves it as the template named by `key`, then selects it + loads its placeholder
  // fields so you can fill values and Create + render.
  const genComp = useMutation({
    mutationFn: (args: { key: string; brief: string }) => graphicsApi.genComposition(slug, args),
    onMutate: () => push(t("toast.genCompStarted"), "run"),
    onError: (e: Error) => push(`composition: ${e.message}`, "err"),
    onSuccess: (r) => {
      setNewComp(r.composition);
      setNewFields(JSON.stringify(r.fields ?? {}, null, 2));
      qc.invalidateQueries({ queryKey: ["hfTemplates"] });
      qc.invalidateQueries({ queryKey: ["titles", slug] });   // card now exists → show it in the grid
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      selectTitle(r.composition);
      setCompGenerated(true);
      push(t("toast.compCreated", { composition: r.composition, count: r.placeholders.length }), "ok");
    },
  });

  function submitNewTitle() {
    let fields: Record<string, unknown> = {};
    try { fields = JSON.parse(newFields || "{}"); }
    catch { push(t("toast.fieldsInvalidJson"), "err"); return; }
    if (!newKey.trim()) { push(t("toast.keyRequired"), "err"); return; }
    if (!newComp) { push(t("toast.compositionRequired"), "err"); return; }
    newTitle.mutate({ key: newKey.trim(), composition: newComp, fields });
  }

  function submitRegenThumb() {
    let fields: Record<string, unknown> = {};
    try { fields = JSON.parse(thumbFields || "{}"); }
    catch { push(t("toast.fieldsInvalidJson"), "err"); return; }
    regenThumb.mutate(fields);
  }

  const renderAllMissing = () => {
    const ts = (titles.data?.titles ?? []).filter(
      (ti) => ti.configured && (ti.status === "missing" || ti.status === "stale")
    );
    if (!ts.length) { push(t("toast.noMissingTitles"), "info"); return; }
    push(t("toast.queuingRenders", { count: ts.length }), "run");
    ts.forEach((ti, i) => setTimeout(() => regen.mutate(ti.key), i * 300));
  };

  const list = titles.data?.titles ?? [];
  const cards = list.filter((ti) => ti.scope !== "hyperframes");
  const hfStrip = list.filter((ti) => ti.scope === "hyperframes");
  const renderedCount = cards.filter((c) => c.status === "rendered" || c.status === "shared").length;

  const cur = useMemo(
    () => cards.find((ti) => ti.key === selectedKey) ?? cards[0],
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
          <div className="panel-title">{t("graphics.previewTitle")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {cur ? cur.key : t("graphics.previewSelectHint")}</span></div>
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
                      ? t("graphics.sharedFileNotFound")
                      : `episodes/${slug}/titles/${cur.key}.mp4 (not built)`}
                  </div>
                </div>
              )}
            </div>
            <div className="grid grid-cols-[80px_1fr] gap-x-2 gap-y-1 text-[12px] flex-none">
              <span className="label-tiny">{t("graphics.metaKey")}</span><span className="font-mono">{cur.key}</span>
              <span className="label-tiny">{t("graphics.metaLayout")}</span>
              <span className="font-mono">
                {cur.configured
                  ? (cur.composition ?? "—")
                  : <span className="text-txt-faint">{t("graphics.bespokeNoLayout")}</span>}
              </span>
              <span className="label-tiny">{t("graphics.metaScope")}</span><span>{cur.scope}</span>
              <span className="label-tiny">{t("graphics.metaStatus")}</span><span>{cur.status}</span>
            </div>
            <div className="flex items-center gap-2 flex-none">
              {cur.configured ? (
                <>
                  <button className="btn btn-cyan" disabled={!!busy[`title:${cur.key}`]}
                    title={t("graphics.regenBtnTitle")}
                    onClick={() => regen.mutate(cur.key)}>
                    <IRegen /> {t("graphics.regenBtn")}
                  </button>
                  <button className="btn"
                    title={t("graphics.editBtnTitle")}
                    onClick={() => openNewFor(cur.key)}>{t("graphics.editBtn")}</button>
                  <RegenNotes onSubmit={() => regen.mutate(cur.key)} />
                </>
              ) : (
                <button className="btn btn-cyan"
                  title={t("graphics.configureBtnTitle")}
                  onClick={() => openNewFor(cur.key)}>
                  <IRegen /> {t("graphics.configureBtn")}
                </button>
              )}
            </div>
            {!cur.configured && (
              <p className="text-txt-faint text-[11px] flex-none -mt-1">
                {t("graphics.bespokeHint")}
              </p>
            )}
          </>
        ) : (
          <div className="flex-1 grid place-items-center text-txt-faint">{t("graphics.noTitleSelected")}</div>
        )}
      </section>

      {/* RIGHT — title-card palette (click → preview on the left) + YouTube thumbnail */}
      <aside className="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <section className="panel flex flex-col">
          <header className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">{t("graphics.titleCardsPanel")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {t("graphics.titleCardsClickHint")}</span></div>
            <span className="seg-readout">{renderedCount}<span className="text-txt-faint">/{cards.length}</span></span>
          </header>
          <div className="p-2 grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(104px, 1fr))" }}>
            {cards.map((ti) => {
              const active = selectedKey === ti.key;
              const isBusy = !!busy[`title:${ti.key}`];
              return (
                <div
                  key={ti.key}
                  onClick={() => selectTitle(ti.key)}
                  title={t("graphics.cardClickToPreview")}
                  className={"hairline-soft text-left p-0 overflow-hidden rounded transition-colors cursor-pointer " + (active ? "border-amber" : "")}
                  style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)" } : {}}
                >
                  <div className="bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
                    {ti.exists ? (
                      <video
                        key={mediaUrl.titlePreview(slug, ti.key) + (ti.mtime ?? "")}
                        src={mediaUrl.titlePreview(slug, ti.key)}
                        autoPlay muted loop playsInline
                        className="w-full h-full object-contain pointer-events-none"
                      />
                    ) : (
                      <div className="text-center">
                        <Badge status={isBusy ? "running" : ti.status} />
                        <div className="label-tiny mt-1">
                          {ti.scope === "shared"
                            ? (ti.status === "missing" ? t("graphics.sharedNotFound") : t("graphics.shared"))
                            : `${ti.key}.mp4`}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-between px-2 py-1 bg-bg-2">
                    <span className="font-mono text-[11px] truncate" title={ti.key}>{ti.key}</span>
                    <span onClick={(e) => e.stopPropagation()} className="flex items-center gap-1">
                      <button
                        className="btn p-1"
                        title={ti.configured
                          ? t("graphics.cardRegenTitle")
                          : t("graphics.cardConfigureTitle")}
                        disabled={isBusy}
                        onClick={() => (ti.configured ? regen.mutate(ti.key) : openNewFor(ti.key))}
                      ><IRegen /></button>
                    </span>
                  </div>
                </div>
              );
            })}
            {cards.length === 0 && (
              <div className="text-txt-faint col-span-full p-2 text-[12px]">{t("graphics.noTitleAssets")}</div>
            )}
          </div>
          <div className="px-3 py-2 border-t hairline-soft flex items-center gap-2">
            <button className="btn btn-cyan" onClick={openNew}>{t("graphics.newTitleCardBtn")}</button>
            <button className="btn btn-amber" onClick={renderAllMissing}><IRegen /> {t("graphics.renderMissingBtn")}</button>
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
            <div className="panel-title">{t("graphics.youtubeThumbnailPanel")}</div>
            <button className="btn btn-cyan" disabled={!!busy.ythumb} onClick={() => setThumbOpen(true)}><IRegen /> {t("graphics.regenerateBtn")}</button>
          </div>
          <div className="p-3 flex flex-col gap-2">
            <button
              className="bg-black hairline-soft rounded overflow-hidden grid place-items-center cursor-zoom-in p-0"
              style={{ aspectRatio: "16/9" }}
              title={t("graphics.thumbClickTitle")}
              onClick={() => setThumbViewOpen(true)}
            >
              <img
                key={(thumbOverride ?? graphicsApi.ythumbPreviewUrl(slug)) + `?b=${thumbBust}`}
                src={thumbOverride ?? `${graphicsApi.ythumbPreviewUrl(slug)}?b=${thumbBust}`}
                alt={t("graphics.thumbAlt")}
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
              <span className="label-tiny">{t("graphics.renderLogLabel")}</span>
              <button className="btn p-0.5 text-[11px]" onClick={() => setLogLines([])}>{t("graphics.clearBtn")}</button>
            </div>
            <pre className="logtail mx-3 my-3" style={{ height: 120 }}>{logLines.join("\n")}</pre>
          </section>
        )}
      </aside>

      <Modal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        width={640}
        title={editMode ? t("graphics.editModalTitle") : t("graphics.newModalTitle")}
        footer={
          <>
            <span className="text-txt-faint text-[11px] mr-auto">
              {editMode ? t("graphics.editModalFooterHint") : t("graphics.newModalFooterHint")}
            </span>
            <button className="btn" onClick={() => setNewOpen(false)}>{t("common.cancel")}</button>
            <button className="btn btn-cyan"
              disabled={newTitle.isPending || (!!newBrief.trim() && !compGenerated)}
              title={(!!newBrief.trim() && !compGenerated) ? t("graphics.createPendingBriefTitle") : ""}
              onClick={submitNewTitle}>{editMode ? t("graphics.saveRenderBtn") : t("graphics.createRenderBtn")}</button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {/* STEP 1 — name */}
          <Step n={1} title={t("graphics.step1Title")} hint={t("graphics.step1Hint")}>
            {editMode ? (
              <div className="flex items-center gap-2 text-[12px]">
                <span className="font-mono text-amber">{newKey}</span>
                <span className="text-txt-faint text-[11px]">{t("graphics.cantRenameHint")}</span>
              </div>
            ) : (
              <Field label="" value={newKey} onChange={setNewKey} placeholder={t("graphics.keyPlaceholder")} monospace />
            )}
          </Step>

          {/* STEP 2 — layout (composition) */}
          <Step n={2} title={t("graphics.step2Title")} hint={t("graphics.step2Hint")}>
            {legacyNote && (
              <div className="hairline-soft rounded p-2 text-[11px] text-txt-dim mb-2">
                <span className="label-tiny text-amber">{t("graphics.bespokeCardLabel")}</span> — {t("graphics.bespokeCardDesc")}
                <div className="mt-1 font-mono text-txt-faint break-words">{legacyNote}</div>
              </div>
            )}
            <div className="grid grid-cols-[1fr_180px] gap-3 items-start">
              <Field
                label={t("graphics.compositionLabel")}
                value={newComp}
                onChange={onPickComposition}
                options={Array.from(new Set([newComp, ...templateOptions].filter(Boolean))) as string[]}
              />
              <CompPreview comp={newComp} />
            </div>
            {/* Generate a whole NEW composition (animated card HTML) from a brief, via local Qwen. */}
            <details className="hairline-soft rounded mt-2">
              <summary className="px-2 py-1.5 cursor-pointer label-tiny select-none">{t("graphics.designWithAiSummary")}</summary>
              <div className="p-2 border-t hairline-soft flex flex-col gap-2">
                <p className="text-txt-faint text-[11px]">
                  {t("graphics.designWithAiHelp")}
                </p>
                <Field label={t("graphics.briefLabel")} value={newBrief} onChange={(v) => { setNewBrief(v); setCompGenerated(false); }} rows={3}
                  placeholder={t("graphics.briefPlaceholder")} />
                <button
                  className="btn btn-amber self-start"
                  disabled={genComp.isPending || !newKey.trim() || !newBrief.trim()}
                  title={t("graphics.genCompBtnTitle")}
                  onClick={() => genComp.mutate({ key: newKey.trim(), brief: newBrief })}
                >✨ {genComp.isPending ? t("graphics.generatingComp") : t("graphics.generateCompBtn")}</button>
                {!newKey.trim() && newBrief.trim() && (
                  <div className="text-[10px] text-amber">{t("graphics.nameFirstWarning")}</div>
                )}
                {newBrief.trim() && !compGenerated && newKey.trim() && (
                  <div className="text-[10px] text-amber">{t("graphics.generateFirstWarning")}</div>
                )}
                {compGenerated && (
                  <div className="text-[10px] text-emerald-400">✓ {t("graphics.compGeneratedSuccess", { key: newKey.trim() })}</div>
                )}
              </div>
            </details>
          </Step>

          {/* STEP 3 — text (fields) */}
          <Step n={3} title={t("graphics.step3Title")} hint={t("graphics.step3Hint")}>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Field label={t("graphics.cardTypeLabel")} value={newCardType} onChange={setNewCardType} options={titleCardTypes} />
              </div>
              <button
                className="btn btn-amber whitespace-nowrap"
                disabled={genText.isPending}
                title={t("graphics.writeTextBtnTitle")}
                onClick={() => genText.mutate({ card_type: newCardType, target: "title" })}
              >✨ {genText.isPending ? t("graphics.writingText") : t("graphics.writeTextBtn")}</button>
            </div>
            {CARD_TYPE_BLURB_KEY[newCardType] && (
              <p className="text-txt-faint text-[10px] mt-1">{t(CARD_TYPE_BLURB_KEY[newCardType])}</p>
            )}
            <p className="text-txt-faint text-[10px]">
              {t("graphics.cardTypeNote")}
            </p>
            <Field label={t("graphics.fieldsJsonLabel")} value={newFields} onChange={setNewFields} rows={6} monospace />
          </Step>
        </div>
      </Modal>

      <Modal
        open={thumbOpen}
        onClose={() => setThumbOpen(false)}
        title={t("graphics.thumbModalTitle")}
        footer={
          <>
            <button className="btn" onClick={() => setThumbOpen(false)}>{t("common.cancel")}</button>
            <button className="btn btn-cyan" disabled={regenThumb.isPending} onClick={submitRegenThumb}>{t("graphics.regenerateBtn")}</button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-txt-dim text-[12px]">
            {t("graphics.thumbModalDesc", { slug })}
          </p>
          <div className="flex justify-end">
            <button
              className="btn btn-amber"
              disabled={genText.isPending}
              title={t("graphics.writeThumbBtnTitle")}
              onClick={() => genText.mutate({ card_type: "youtube_thumb", target: "thumb" })}
            >✨ {genText.isPending ? t("graphics.writingText") : t("graphics.writeWithAiBtn")}</button>
          </div>
          <Field label={t("graphics.fieldsJsonLabel")} value={thumbFields} onChange={setThumbFields} rows={6} monospace />
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

/** A numbered step block for the New/Edit title-card modal — keeps the workflow legible. */
function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <span className="grid place-items-center w-5 h-5 rounded-full bg-bg-2 hairline-soft text-[11px] text-amber font-mono flex-none self-center">{n}</span>
        <span className="text-[13px] text-txt">{title}</span>
      </div>
      {hint && <p className="text-txt-faint text-[11px] pl-7 -mt-1">{hint}</p>}
      <div className="pl-7">{children}</div>
    </div>
  );
}

/** Live thumbnail of a HyperFrames composition, served read-only from the template dir.
 * Renders the template HTML in a sandboxed iframe scaled to fit; ‹TOKENS› show where each
 * field lands. We jump the GSAP timeline to its final frame so the card is fully revealed
 * (templates start paused at frame 0 for deterministic seek-rendering). */
function CompPreview({ comp }: { comp: string }) {
  const t = useT();
  if (!comp) {
    return (
      <div className="hairline-soft rounded bg-black grid place-items-center text-txt-faint text-[10px]" style={{ width: 180, height: 180 }}>
        {t("graphics.pickLayoutHint")}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1 flex-none">
      <div className="hairline-soft rounded bg-black overflow-hidden" style={{ width: 180, height: 180 }}>
        <iframe
          key={comp}
          title={`preview of ${comp}`}
          src={`/api/hf/template-assets/${encodeURIComponent(comp)}/index.html`}
          sandbox="allow-scripts allow-same-origin"
          scrolling="no"
          onLoad={(e) => {
            try {
              const w = (e.currentTarget as HTMLIFrameElement).contentWindow as any;
              const tl = w?.__timelines?.main;
              if (tl?.progress) tl.progress(1); // jump to fully-revealed frame
            } catch { /* no timeline / blocked — leave as the template renders it */ }
          }}
          style={{ width: 1024, height: 1024, transform: "scale(0.17578)", transformOrigin: "top left", border: 0, pointerEvents: "none" }}
        />
      </div>
      <span className="label-tiny text-center text-txt-faint">{t("graphics.liveLayoutHint")}</span>
    </div>
  );
}
