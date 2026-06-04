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
  });

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
  useEffect(() => {
    if (!newComp && templateOptions.length) setNewComp(templateOptions[0]);
  }, [templateOptions, newComp]);
  // Open the New-title modal pre-filled for an existing (string/shared) entry so it
  // becomes object-form HyperFrames and can render. Used for non-configured titles.
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
      <section className="panel flex flex-col min-h-0">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">TITLE CARDS <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ manifest.title_assets</span></div>
          <div className="flex items-center gap-2">
            <span className="seg-readout">{renderedCount}<span className="text-txt-faint">/{cards.length}</span> READY</span>
            <button className="btn btn-cyan" onClick={() => setNewOpen(true)}>
              + New title card
            </button>
            <button className="btn btn-amber" onClick={renderAllMissing}>
              <IRegen /> Render all missing
            </button>
          </div>
        </header>
        <div className="overflow-y-auto flex-1 p-3 grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
          {cards.map((t) => {
            const active = selectedKey === t.key;
            const isBusy = !!busy[`title:${t.key}`];
            return (
              <button
                key={t.key}
                onClick={() => selectTitle(t.key)}
                className={"hairline-soft text-left p-0 overflow-hidden rounded transition-colors " + (active ? "border-amber" : "")}
                style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)" } : {}}
              >
                <div className="bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
                  {t.exists ? (
                    <video
                      key={mediaUrl.titlePreview(slug, t.key) + (t.mtime ?? "")}
                      src={mediaUrl.titlePreview(slug, t.key)}
                      autoPlay
                      muted
                      loop
                      playsInline
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <div className="text-center">
                      <Badge status={isBusy ? "running" : t.status} />
                      <div className="label-tiny mt-1">
                        {t.scope === "shared"
                          ? (t.status === "missing" ? "shared — not found" : "shared assets/titles/")
                          : `${t.key}.mp4`}
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between px-2 py-1.5 bg-bg-2">
                  <span className="font-mono">{t.key}</span>
                  <span onClick={(e) => e.stopPropagation()} className="flex items-center gap-1">
                    <button
                      className="btn p-1"
                      title={t.configured ? "Regen via HyperFrames" : "Configure + generate (pick a composition)"}
                      disabled={isBusy}
                      onClick={() => (t.configured ? regen.mutate(t.key) : openNewFor(t.key))}
                    ><IRegen /></button>
                    {t.configured && <RegenNotes onSubmit={() => regen.mutate(t.key)} />}
                  </span>
                </div>
              </button>
            );
          })}
          {cards.length === 0 && (
            <div className="text-txt-faint col-span-full p-3">No title_assets in manifest.</div>
          )}
        </div>
        <div className="px-3 py-2 border-t hairline-soft flex items-center gap-3 flex-wrap">
          <span className="label-tiny">HyperFrames · episodes/{slug}/hyperframes/</span>
          {hfStrip.length === 0 ? (
            <span className="text-txt-faint text-[12px]">no .html compositions present</span>
          ) : hfStrip.map((h) => (
            <span key={h.key} className="hairline-soft px-2 py-1 inline-flex items-center gap-1.5 rounded">
              <Dot status={h.status} />
              <span className="font-mono">{h.key}.html</span>
              <span className="text-txt-faint text-[11px]">{h.hint}</span>
            </span>
          ))}
        </div>
        {logLines.length > 0 && (
          <div className="border-t hairline-soft">
            <div className="px-3 py-1 flex items-center justify-between">
              <span className="label-tiny">render log tail</span>
              <button className="btn p-0.5 text-[11px]" onClick={() => setLogLines([])}>clear</button>
            </div>
            <pre className="logtail mx-3 mb-3" style={{ height: 140 }}>{logLines.join("\n")}</pre>
          </div>
        )}
      </section>

      <aside className="panel p-3 flex flex-col gap-3 overflow-y-auto">
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
                autoPlay
                muted
                loop
                playsInline
                controls
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
            <div className="flex flex-col gap-1">
              <span className="label-tiny">manifest hint</span>
              <p className="whitespace-pre-wrap text-[12px]">{cur.hint || "—"}</p>
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
            </div>
            <p className="text-txt-faint text-[11px]">
              {cur.scope === "shared"
                ? "Reused from shared assets/titles/. ‘Configure + generate’ builds a per-episode HyperFrames version instead."
                : cur.configured
                  ? "Rendered via HyperFrames from its composition + fields."
                  : "New per-episode title — pick a composition + fields to generate it (writes the object form to the manifest)."}
            </p>
          </>
        ) : (
          <div className="text-txt-faint">No title selected.</div>
        )}

        <div className="panel">
          <div className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">YOUTUBE THUMBNAIL</div>
            <button
              className="btn btn-cyan"
              disabled={!!busy.ythumb}
              onClick={() => setThumbOpen(true)}
            ><IRegen /> Regenerate</button>
          </div>
          <div className="p-3 flex flex-col gap-2">
            <div className="bg-black hairline-soft rounded overflow-hidden grid place-items-center" style={{ aspectRatio: "16/9" }}>
              <img
                key={(thumbOverride ?? graphicsApi.ythumbPreviewUrl(slug)) + `?b=${thumbBust}`}
                src={thumbOverride ?? `${graphicsApi.ythumbPreviewUrl(slug)}?b=${thumbBust}`}
                alt="youtube thumbnail"
                className="w-full h-full object-contain"
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
                onLoad={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "visible"; }}
              />
            </div>
            <VersionArrows
              slug={slug}
              kind="ythumb"
              vkey={slug}
              onView={(u) => setThumbOverride(u)}
              onChanged={() => { setThumbOverride(null); setThumbBust((n) => n + 1); }}
            />
          </div>
        </div>
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
          <Field label="fields (JSON)" value={thumbFields} onChange={setThumbFields} rows={6} monospace />
        </div>
      </Modal>
    </div>
  );
}
