import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { useStore } from "../store";
import { Badge, Dot } from "../components/Badge";
import { RegenNotes } from "../components/RegenNotes";
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

  const renderAllMissing = () => {
    const ts = (titles.data?.titles ?? []).filter(
      (t) => t.scope === "local" && (t.status === "missing" || t.status === "stale")
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
            <button className="btn btn-amber" onClick={renderAllMissing}>
              <IRegen /> Render all missing
            </button>
          </div>
        </header>
        <div className="overflow-y-auto flex-1 p-3 grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
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
                <div className="bg-black grid place-items-center" style={{ aspectRatio: "16/9" }}>
                  {t.scope === "local" && t.exists ? (
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
                        {t.scope === "shared" ? "shared assets/titles/" : `${t.key}.mp4`}
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between px-2 py-1.5 bg-bg-2">
                  <span className="font-mono">{t.key}</span>
                  <span onClick={(e) => e.stopPropagation()} className="flex items-center gap-1">
                    <button
                      className="btn p-1"
                      title="Regen via HyperFrames"
                      disabled={isBusy}
                      onClick={() => regen.mutate(t.key)}
                    ><IRegen /></button>
                    <RegenNotes onSubmit={() => regen.mutate(t.key)} />
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
            {cur.scope === "local" && cur.exists ? (
              <video
                key={mediaUrl.titlePreview(slug, cur.key) + (cur.mtime ?? "")}
                src={mediaUrl.titlePreview(slug, cur.key)}
                autoPlay
                muted
                loop
                playsInline
                controls
                className="w-full bg-black hairline-soft rounded"
                style={{ aspectRatio: "16/9" }}
              />
            ) : (
              <div className="hairline-soft bg-black grid place-items-center" style={{ aspectRatio: "16/9" }}>
                <div className="text-center">
                  <Badge status={cur.status} />
                  <div className="label-tiny mt-2 break-all">
                    {cur.scope === "shared"
                      ? "title resolves from shared assets/titles/"
                      : `episodes/${slug}/titles/${cur.key}.mp4 (missing)`}
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
            <div className="hairline-soft p-2 rounded bg-bg-2 text-[12px]">
              <div className="label-tiny mb-1">to rebuild a per-episode title</div>
              <p className="text-txt-dim">
                Build a HyperFrames composition (see the <code>hyperframes</code>
                {" "}skill) in <code>episodes/{slug}/titles/{cur.key}.html</code>, render
                to mp4, drop it next to the html. Studio v0.7 will wire the regen
                button to do this automatically.
              </p>
            </div>
          </>
        ) : (
          <div className="text-txt-faint">No title selected.</div>
        )}
      </aside>
    </div>
  );
}
