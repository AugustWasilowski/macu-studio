import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api, jobStreamUrl, mediaUrl } from "../api";
import { useStore } from "../store";
import { Badge, Dot } from "../components/Badge";
import { IDL, IFolder, IRegen } from "../components/Icons";
import type { PipelineEvent, PipelineStage, StageKey } from "../types";

const STAGE_KEYS: StageKey[] = ["vo", "masters", "rife", "assemble", "music", "whisper", "srt", "burn"];

export function Assembly({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

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

  // SSE-driven live overlay on top of the at-rest pipeline snapshot
  const [live, setLive] = useState<Record<StageKey, "running" | "done" | "failed" | null>>(() =>
    Object.fromEntries(STAGE_KEYS.map((k) => [k, null])) as any
  );
  const [logLines, setLogLines] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(jobStreamUrl(jobId));
    const ts = () => new Date().toLocaleTimeString("en-GB", { hour12: false });
    const push = (line: string) => setLogLines((L) => [...L.slice(-200), line]);
    es.onmessage = (m) => {
      let ev: PipelineEvent;
      try { ev = JSON.parse(m.data); } catch { return; }
      const n = (ev.n ?? 0) as number;
      const k = STAGE_KEYS[n - 1];
      if (ev.kind === "stage.started" && k) {
        setLive((s) => ({ ...s, [k]: "running" }));
        push(`[${ts()}] stage ${n} ${ev.name} STARTED`);
      } else if (ev.kind === "stage.done" && k) {
        setLive((s) => ({ ...s, [k]: "done" }));
        push(`[${ts()}] stage ${n} ${ev.name} done (${ev.wall_s}s)`);
        // Invalidate downstream queries — pipeline status + final at minimum
        qc.invalidateQueries({ queryKey: ["pipeline", slug] });
      } else if (ev.kind === "stage.error" && k) {
        setLive((s) => ({ ...s, [k]: "failed" }));
        push(`[${ts()}] ERROR stage ${n} ${ev.name}: ${ev.error}`);
      } else if (ev.kind === "job.done") {
        push(`[${ts()}] JOB DONE — ${(ev as any).final ?? ""}`);
        setRunning(false);
        qc.invalidateQueries({ queryKey: ["pipeline", slug] });
        qc.invalidateQueries({ queryKey: ["final", slug] });
        qc.invalidateQueries({ queryKey: ["srt", slug] });
      } else if (ev.kind === "job.error") {
        push(`[${ts()}] JOB ERROR: ${ev.error}`);
        setRunning(false);
      } else if (ev.kind === "job.started") {
        push(`[${ts()}] job started slug=${(ev as any).slug} from=${(ev as any).from_stage ?? 1}`);
      }
    };
    es.addEventListener("end", () => {
      es.close();
    });
    es.onerror = () => {
      // browser auto-reconnects; we mostly just note it
    };
    return () => { es.close(); };
  }, [jobId, qc, slug]);

  const run = useMutation({
    mutationFn: (body: { from_stage?: number; only?: number }) => api.run(slug, body),
    onMutate: () => {
      setLive(Object.fromEntries(STAGE_KEYS.map((k) => [k, null])) as any);
      setLogLines([]);
      setRunning(true);
    },
    onSuccess: (r) => {
      setJobId(r.job_id);
      push("RUN queued (" + r.job_id + ")", "run");
    },
    onError: (e: Error) => {
      setRunning(false);
      push("Render failed: " + e.message, "err");
    },
  });

  const stagesView: PipelineStage[] = useMemo(() => {
    if (!pipeline.data) return [];
    return pipeline.data.stages.map((s) => {
      const overlay = live[s.key];
      return overlay ? { ...s, status: overlay === "failed" ? "failed" : overlay } : s;
    });
  }, [pipeline.data, live]);

  return (
    <div className="grid grid-cols-[1fr_1fr_1fr] gap-3 h-full">
      {/* Left — pipeline control */}
      <section className="panel p-3 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="panel-title">Pipeline</div>
          <div className="text-txt-faint label-tiny">slug · {slug}</div>
        </div>
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left label-tiny">
              <th>St</th><th>Name</th><th>Last</th><th></th>
            </tr>
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
                  <button
                    className="btn"
                    disabled={running}
                    onClick={() => run.mutate({ only: s.n })}
                    title={`Run only stage ${s.n}`}
                  >
                    ▶
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center gap-2 pt-2 border-t border-[var(--line-soft)]">
          <select
            id="from-stage"
            className="input"
            defaultValue="1"
          >
            {stagesView.map((s) => <option key={s.key} value={s.n}>From {s.n}. {s.name}</option>)}
          </select>
          <button
            className="btn"
            disabled={running}
            onClick={() => {
              const v = parseInt((document.getElementById("from-stage") as HTMLSelectElement).value, 10);
              run.mutate({ from_stage: v });
            }}
          >Run</button>
        </div>
        <button
          className="btn btn-amber btn-big mt-2"
          disabled={running}
          onClick={() => run.mutate({})}
        >RENDER FULL EPISODE</button>
        <div className="label-tiny mt-2">log tail</div>
        <pre className="logtail">{logLines.length === 0 ? "(no events yet — click a Run button)" : logLines.join("\n")}</pre>
      </section>

      {/* Center — subtitles */}
      <section className="panel p-3 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="panel-title">Subtitles</div>
          <button className="btn" disabled={running} onClick={() => run.mutate({ only: 8 })}>
            <IRegen /> Re-burn subs only
          </button>
        </div>
        <div className="overflow-y-auto flex-1 max-h-[calc(100vh-180px)] hairline-soft rounded">
          {(srt.data?.entries.length ?? 0) === 0 && (
            <div className="p-3 text-txt-faint">No SRT yet. Run stage 7 first.</div>
          )}
          {srt.data?.entries.map((e) => (
            <SrtRow key={e.i} slug={slug} entry={e} onSave={(text) => {
              const next = srt.data!.entries.map((x) => x.i === e.i ? { ...x, text } : x);
              api.putSrt(slug, next).then(() => qc.invalidateQueries({ queryKey: ["srt", slug] }));
            }} />
          ))}
        </div>
      </section>

      {/* Right — final output */}
      <section className="panel p-3 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="panel-title">Final output</div>
          {final.data?.exists && <Badge status="rendered" />}
        </div>
        {!final.data?.exists ? (
          <div className="text-txt-faint flex-1 grid place-items-center">No final mp4 yet.</div>
        ) : (
          <>
            <video
              key={mediaUrl.finalVideo(slug) + (final.data.mtime ?? "")}
              src={mediaUrl.finalVideo(slug)}
              controls
              className="w-full bg-black rounded"
              style={{ aspectRatio: "1 / 1", maxHeight: 380 }}
            />
            <div className="text-[12px] grid grid-cols-2 gap-1.5">
              <span className="label-tiny">size</span>
              <span className="text-cyan">{final.data.size_mb} MB</span>
              <span className="label-tiny">duration</span>
              <span className="text-cyan">{final.data.duration_s ?? "—"} s</span>
              <span className="label-tiny">srt</span>
              <span>{final.data.srt_exists ? "yes" : "no"}</span>
            </div>
            <div className="flex gap-2">
              <a className="btn" href={mediaUrl.finalVideo(slug)} download={`${slug}.mp4`}>
                <IDL /> Download
              </a>
              <button
                className="btn"
                onClick={() => navigator.clipboard.writeText(final.data!.path).then(() => push("Path copied", "ok"))}
              >
                <IFolder /> Copy path
              </button>
            </div>
            {final.data.thumb_exists && (
              <img
                key={mediaUrl.finalThumb(slug) + (final.data.mtime ?? "")}
                src={mediaUrl.finalThumb(slug)}
                alt="thumbs"
                className="w-full rounded mt-2 hairline-soft"
              />
            )}
            <div className="label-tiny mt-1 break-all">{final.data.path}</div>
          </>
        )}
      </section>
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
    <div className="flex items-baseline gap-2 px-2 py-1 border-b border-[var(--line-soft)]">
      <span className="seg-readout cyan w-10 text-center">{entry.i}</span>
      <span className="text-cyan text-[11px]">{entry.start} → {entry.end}</span>
      {editing ? (
        <input
          ref={ref}
          className="input flex-1"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => { setEditing(false); if (draft !== entry.text) onSave(draft); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); }
            if (e.key === "Escape") { setDraft(entry.text); setEditing(false); }
          }}
        />
      ) : (
        <span className="flex-1 cursor-text" onClick={() => setEditing(true)}>{entry.text}</span>
      )}
    </div>
  );
}
