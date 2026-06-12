import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api, jobStreamUrl, mediaUrl } from "../api";
import { higgsfieldApi } from "../api/higgsfield";
import type { HfEstimate } from "../api/higgsfield";
import { useStore, DEFAULT_RUN } from "../store";
import { Badge, Dot } from "../components/Badge";
import { Collapsible } from "../components/Collapsible";
import { Modal } from "../components/Modal";
import { IDL, IFolder, IRegen } from "../components/Icons";
import { DopeSheet } from "./DopeSheet";
import { Timeline } from "./Timeline";
import { LocalizeModal } from "./LocalizeModal";
import { useT } from "../i18n";
import { isCloudKind } from "../types";
import type { FinalInfo, PipelineEvent, PipelineStage, SrtEntry, StageKey } from "../types";

const STAGE_KEYS: StageKey[] = ["vo", "masters", "rife", "assemble", "music", "whisper", "srt", "burn"];

export function Assembly({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [localizeOpen, setLocalizeOpen] = useState(false);

  const pipeline = useQuery({
    queryKey: ["pipeline", slug],
    queryFn: () => api.pipeline(slug),
    refetchInterval: false,
  });
  const final = useQuery({
    queryKey: ["final", slug],
    queryFn: () => api.final(slug),
    refetchInterval: false,
  });
  const srt = useQuery({
    queryKey: ["srt", slug],
    queryFn: () => api.srt(slug),
  });

  // Run state lives in the store (keyed by slug) so the log tail + stage state
  // survive leaving the Assembly tab. On return the SSE reconnects from `seen`
  // (?since=) — no replayed or missed events.
  const runState = useStore((s) => s.runs[slug]) ?? DEFAULT_RUN;
  const resetRun = useStore((s) => s.resetRun);
  const patchRun = useStore((s) => s.patchRun);
  const appendRunLog = useStore((s) => s.appendRunLog);
  const setRunLive = useStore((s) => s.setRunLive);
  const live = runState.live;
  const logLines = runState.logLines;
  const running = runState.running;

  // On mount / slug change, re-attach to an in-progress render (after a reload, or
  // one started from another tab/CLI) so the log tail rebuilds from the job's events.
  useEffect(() => {
    let alive = true;
    api.activePipelineJob(slug).then((r) => {
      if (!alive || !r.job_id) return;
      if (useStore.getState().runs[slug]?.jobId === r.job_id) return; // already tracking it
      patchRun(slug, { jobId: r.job_id, running: true, seen: 0, logLines: [], live: {} });
    }).catch(() => {});
    return () => { alive = false; };
  }, [slug, patchRun]);

  useEffect(() => {
    if (!runState.jobId || !runState.running) return;
    const jobId = runState.jobId;
    const ts = () => new Date().toLocaleTimeString("en-GB", { hour12: false });
    let es: EventSource | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const open = () => {
      if (closed) return;
      // Always (re)open from the CURRENT seen count, not a value frozen at first
      // open — otherwise a transient disconnect's auto-reconnect replays old events
      // and duplicates the log / inflates `seen`.
      const since = useStore.getState().runs[slug]?.seen ?? 0;
      es = new EventSource(jobStreamUrl(jobId, since));
      es.onmessage = (m) => {
        let ev: PipelineEvent;
        try { ev = JSON.parse(m.data); } catch { return; }
        const seen = (useStore.getState().runs[slug]?.seen ?? 0) + 1;
        const n = (ev.n ?? 0) as number;
        const k = STAGE_KEYS[n - 1];
        let line = "";
        if (ev.kind === "stage.started" && k) { setRunLive(slug, k, "running"); line = `[${ts()}] stage ${n} ${ev.name} STARTED`; }
        else if (ev.kind === "stage.done" && k) { setRunLive(slug, k, "done"); line = `[${ts()}] stage ${n} ${ev.name} done (${ev.wall_s}s)`; qc.invalidateQueries({ queryKey: ["pipeline", slug] }); }
        else if (ev.kind === "stage.error" && k) { setRunLive(slug, k, "failed"); line = `[${ts()}] ERROR stage ${n} ${ev.name}: ${ev.error}`; }
        else if (ev.kind === "job.done") { line = `[${ts()}] JOB DONE — ${(ev as any).final ?? ""}`; patchRun(slug, { running: false }); qc.invalidateQueries({ queryKey: ["pipeline", slug] }); qc.invalidateQueries({ queryKey: ["final", slug] }); qc.invalidateQueries({ queryKey: ["srt", slug] }); }
        else if (ev.kind === "job.error") { line = `[${ts()}] JOB ERROR: ${ev.error}`; patchRun(slug, { running: false }); }
        else if (ev.kind === "job.started") { line = `[${ts()}] job started slug=${(ev as any).slug} from=${(ev as any).from_stage ?? 1}`; }
        if (line) appendRunLog(slug, line, seen); else patchRun(slug, { seen });
      };
      es.addEventListener("end", () => { closed = true; es?.close(); });
      es.onerror = () => {
        // Close the browser's pending auto-reconnect (it would replay from the old
        // `since`) and reopen from the live seen after a short backoff.
        if (closed) return;
        es?.close();
        retry = setTimeout(open, 1000);
      };
    };

    open();
    return () => { closed = true; clearTimeout(retry); es?.close(); };
  }, [slug, runState.jobId, runState.running, qc, patchRun, appendRunLog, setRunLive]);

  const run = useMutation({
    mutationFn: (body: { from_stage?: number; only?: number }) => api.run(slug, body),
    onMutate: () => resetRun(slug),
    onSuccess: (r) => {
      patchRun(slug, { jobId: r.job_id });
      push(t("toast.runQueued", { jobId: r.job_id }), "run");
    },
    onError: (e: Error) => {
      patchRun(slug, { running: false });
      push(t("toast.renderFailed", { message: e.message }), "err");
    },
  });

  const stagesView: PipelineStage[] = useMemo(() => {
    if (!pipeline.data) return [];
    return pipeline.data.stages.map((s) => {
      const overlay = live[s.key];
      return overlay ? { ...s, status: overlay === "failed" ? "failed" : overlay } : s;
    });
  }, [pipeline.data, live]);

  // ---- Higgsfield cost gate ----
  // A run that includes stage 2 on an episode with cloud shots may bill credits;
  // show the per-shot estimate first. Cached shots are free → dialog auto-skips
  // when the total is 0 with no unknowns.
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });
  const hasCloud = useMemo(() => {
    const cs = (manifest.data as any)?.cues ?? [];
    return cs.some((c: any) => (c.shots ?? []).some((s: any) => isCloudKind(s.kind)));
  }, [manifest.data]);
  const [costGate, setCostGate] = useState<null | {
    body: { from_stage?: number; only?: number };
    estimate: HfEstimate | null;
    error: string | null;
    loading: boolean;
  }>(null);

  const onRun = (body: { from_stage?: number; only?: number }) => {
    const touchesStage2 = body.only != null ? body.only === 2 : (body.from_stage ?? 1) <= 2;
    if (!hasCloud || !touchesStage2) { run.mutate(body); return; }
    setCostGate({ body, estimate: null, error: null, loading: true });
    higgsfieldApi.estimate(slug).then((est) => {
      if (est.total_credits === 0 && est.unknown_costs === 0) {
        setCostGate(null);
        run.mutate(body); // everything cached — nothing to bill
      } else {
        setCostGate({ body, estimate: est, error: null, loading: false });
      }
    }).catch((e) => {
      setCostGate({ body, estimate: null, error: e instanceof Error ? e.message : String(e), loading: false });
    });
  };

  return (
    <div className="grid grid-cols-[640px_minmax(0,1fr)_360px] grid-rows-[minmax(0,1fr)] gap-3 h-full min-h-0">
      {/* LEFT — dope sheet (graphics onto cues), full height */}
      <DopeSheet slug={slug} />

      {/* CENTER — timeline (cues / VO / shots / graphics / music / sfx + asset drawer) */}
      <Timeline slug={slug} />

      {/* RIGHT — the assembly controls, re-housed as collapsible panels */}
      <aside className="flex flex-col gap-3 min-h-0 overflow-y-auto">
        <Collapsible title={t("assembly.pipelineTitle", { slug })} storageKey="macu.asm.pipeline" bare>
          <PipelinePanel stagesView={stagesView} running={running} onRun={onRun} logLines={logLines} />
        </Collapsible>
        <Collapsible title={t("assembly.subtitlesTitle")} storageKey="macu.asm.srt" defaultOpen={false} bare>
          <SrtPanel slug={slug} entries={srt.data?.entries ?? []} running={running} onRun={onRun}
            onSaved={() => qc.invalidateQueries({ queryKey: ["srt", slug] })} />
        </Collapsible>
        <Collapsible title={t("assembly.finalOutputTitle")} storageKey="macu.asm.final" bare>
          <FinalPanel slug={slug} final={final.data}
            onCopy={(p) => navigator.clipboard.writeText(p).then(() => push(t("toast.pathCopied"), "ok"))}
            onLocalize={() => setLocalizeOpen(true)} />
        </Collapsible>
      </aside>
      <LocalizeModal slug={slug} open={localizeOpen} onClose={() => setLocalizeOpen(false)} />
      <CostGateDialog
        gate={costGate}
        onCancel={() => setCostGate(null)}
        onConfirm={() => { const b = costGate?.body; setCostGate(null); if (b) run.mutate(b); }}
      />
    </div>
  );
}

function CostGateDialog({ gate, onCancel, onConfirm }: {
  gate: null | { body: { from_stage?: number; only?: number }; estimate: HfEstimate | null; error: string | null; loading: boolean };
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const t = useT();
  if (!gate) return null;
  const est = gate.estimate;
  return (
    <Modal
      open
      onClose={onCancel}
      title={t("assembly.costTitle")}
      width={520}
      footer={
        <>
          <button className="btn" onClick={onCancel}>{t("common.cancel")}</button>
          <button className="btn btn-amber" disabled={gate.loading} onClick={onConfirm}>
            {t("assembly.costRenderAnyway")}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-2 text-[12px]">
        {gate.loading && <div className="text-txt-dim">{t("assembly.costLoading")}</div>}
        {gate.error && (
          <div className="text-red">{t("assembly.costError", { msg: gate.error })}</div>
        )}
        {est && (
          <>
            <div className="max-h-[260px] overflow-y-auto hairline-soft rounded">
              {est.shots.map((s) => (
                <div key={s.id} className={"flex items-center gap-2 px-2 py-1 border-b border-[var(--line-soft)] " + (s.cached ? "opacity-50" : "")}>
                  <span>{s.kind === "lipsync" ? "👄" : "☁"}</span>
                  <span className="font-mono flex-1 truncate">{s.id}</span>
                  {s.segments > 1 && <span className="label-tiny">{t("assembly.costSegments", { n: s.segments })}</span>}
                  <span className="font-mono">
                    {s.cached ? t("assembly.costCachedFree")
                      : s.credits == null ? (s.note ?? "?")
                      : t("assembly.costCredits", { n: s.credits })}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between pt-1">
              <span className="label-tiny">{t("assembly.costTotal")}</span>
              <span className="font-mono text-[14px]">{t("assembly.costCredits", { n: est.total_credits })}</span>
            </div>
            {est.balance != null && (
              <div className="flex items-center justify-between">
                <span className="label-tiny">{t("assembly.costBalance", { plan: est.plan ?? "?" })}</span>
                <span className={"font-mono " + (est.sufficient === false ? "text-red" : "")}>{est.balance}</span>
              </div>
            )}
            {est.sufficient === false && (
              <div className="text-red">{t("assembly.costInsufficient")}</div>
            )}
            {est.unknown_costs > 0 && (
              <div className="text-txt-faint">{t("assembly.costUnknowns", { n: est.unknown_costs })}</div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

// ---- right-rail panels (split out of the old 3-column Assembly) ----

function PipelinePanel({ stagesView, running, onRun, logLines }: {
  stagesView: PipelineStage[];
  running: boolean;
  onRun: (b: { from_stage?: number; only?: number }) => void;
  logLines: string[];
}) {
  const t = useT();
  const [fromStage, setFromStage] = useState(1);
  return (
    <div className="p-3 flex flex-col gap-2">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-left label-tiny"><th>{t("assembly.colStage")}</th><th>{t("assembly.colName")}</th><th>{t("assembly.colLast")}</th><th></th></tr>
        </thead>
        <tbody>
          {stagesView.map((s) => (
            <tr key={s.key} className="border-t border-[var(--line-soft)]">
              <td className="py-1.5"><Dot status={s.status} pulse={s.status === "running"} /></td>
              <td className="py-1.5">
                <div className="font-semibold">{s.n}. {s.name}</div>
                <div className="text-txt-faint text-[10px]">{s.note}</div>
              </td>
              <td className="py-1.5 text-txt-dim">{s.last}</td>
              <td className="py-1.5">
                <button className="btn" disabled={running} onClick={() => onRun({ only: s.n })} title={t("assembly.runOnlyStage", { n: s.n })}>▶</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-2 pt-2 border-t border-[var(--line-soft)]">
        <select className="input" value={fromStage} onChange={(e) => setFromStage(parseInt(e.target.value, 10))}>
          {stagesView.map((s) => <option key={s.key} value={s.n}>{t("assembly.fromStage", { n: s.n, name: s.name })}</option>)}
        </select>
        <button className="btn" disabled={running} onClick={() => onRun({ from_stage: fromStage })}>{t("assembly.runBtn")}</button>
      </div>
      <button className="btn btn-amber btn-big mt-2" disabled={running} onClick={() => onRun({})}>{t("assembly.renderFull")}</button>
      <div className="label-tiny mt-2">{t("assembly.logTail")}</div>
      <pre className="logtail">{logLines.length === 0 ? t("assembly.noEvents") : logLines.join("\n")}</pre>
    </div>
  );
}

function SrtPanel({ slug, entries, running, onRun, onSaved }: {
  slug: string;
  entries: SrtEntry[];
  running: boolean;
  onRun: (b: { from_stage?: number; only?: number }) => void;
  onSaved: () => void;
}) {
  const t = useT();
  return (
    <div className="p-3 flex flex-col gap-2">
      <div className="flex items-center justify-end">
        <button className="btn" disabled={running} onClick={() => onRun({ only: 8 })}><IRegen /> {t("assembly.reburnSubs")}</button>
      </div>
      <div className="overflow-y-auto max-h-[340px] hairline-soft rounded">
        {entries.length === 0 && <div className="p-3 text-txt-faint">{t("assembly.noSrt")}</div>}
        {entries.map((e) => (
          <SrtRow key={e.i} slug={slug} entry={e} onSave={(text) => {
            const next = entries.map((x) => x.i === e.i ? { ...x, text } : x);
            api.putSrt(slug, next).then(onSaved);
          }} />
        ))}
      </div>
    </div>
  );
}

function FinalPanel({ slug, final, onCopy, onLocalize }: {
  slug: string;
  final: FinalInfo | undefined;
  onCopy: (path: string) => void;
  onLocalize: () => void;
}) {
  const t = useT();
  return (
    <div className="p-3 flex flex-col gap-2">
      <div className="flex items-center justify-end">{final?.exists && <Badge status="rendered" />}</div>
      {!final?.exists ? (
        <div className="text-txt-faint py-6 grid place-items-center">{t("assembly.noFinal")}</div>
      ) : (
        <>
          <video
            key={mediaUrl.finalVideo(slug) + (final.mtime ?? "")}
            src={mediaUrl.finalVideo(slug)}
            controls
            className="w-full bg-black rounded"
            style={{ aspectRatio: "1 / 1", maxHeight: 320 }}
          />
          <div className="text-[12px] grid grid-cols-2 gap-1.5">
            <span className="label-tiny">{t("assembly.labelSize")}</span><span className="text-cyan">{final.size_mb ?? "—"} MB</span>
            <span className="label-tiny">{t("assembly.labelDuration")}</span><span className="text-cyan">{final.duration_s ?? "—"} s</span>
            <span className="label-tiny">{t("assembly.labelSrt")}</span><span>{final.srt_exists ? t("assembly.yes") : t("assembly.no")}</span>
          </div>
          <div className="flex gap-2">
            <a className="btn" href={mediaUrl.finalVideo(slug)} download={`${slug}.mp4`}><IDL /> {t("assembly.download")}</a>
            <button className="btn" onClick={() => onCopy(final.path)}><IFolder /> {t("assembly.copyPath")}</button>
          </div>
          <button className="btn btn-cyan justify-center mt-1" onClick={onLocalize}>{t("assembly.localize")}</button>
          {final.thumb_exists && (
            <img key={mediaUrl.finalThumb(slug) + (final.mtime ?? "")} src={mediaUrl.finalThumb(slug)} alt={t("assembly.thumbsAlt")} className="w-full rounded mt-2 hairline-soft" />
          )}
          <div className="label-tiny mt-1 break-all">{final.path}</div>
        </>
      )}
    </div>
  );
}

function SrtRow({ slug, entry, onSave }: { slug: string; entry: { i: number; start: string; end: string; text: string }; onSave: (t: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.text);
  useEffect(() => { setDraft(entry.text); }, [entry.text]);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);
  void slug;
  return (
    <div className="px-2 py-1.5 border-b border-[var(--line-soft)]">
      <div className="flex items-center gap-2 mb-0.5">
        <span className="seg-readout cyan px-1 text-center">{entry.i}</span>
        <span className="text-cyan text-[11px]">{entry.start} → {entry.end}</span>
      </div>
      {editing ? (
        <input
          ref={ref}
          className="input w-full"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => { setEditing(false); if (draft !== entry.text) onSave(draft); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); }
            if (e.key === "Escape") { setDraft(entry.text); setEditing(false); }
          }}
        />
      ) : (
        <div className="cursor-text text-[12px] leading-snug" onClick={() => setEditing(true)}>{entry.text}</div>
      )}
    </div>
  );
}
