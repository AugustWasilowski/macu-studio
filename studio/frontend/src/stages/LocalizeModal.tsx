import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Modal } from "../components/Modal";
import { useStore } from "../store";
import { useT, LOCALES } from "../i18n";
import { localizeApi, dubUrl, jobStreamUrl, LocalizeJob } from "../api";

type LangState = {
  step: string;          // translate | vo | mix | srt | burn
  voDone?: number;
  voTotal?: number;
  status: "running" | "done" | "error";
  error?: string;
};

const STEP_KEY: Record<string, string> = {
  translate: "localize.step.translate",
  vo: "localize.step.vo",
  mix: "localize.step.mix",
  srt: "localize.step.srt",
  burn: "localize.step.burn",
};

/* Localize an already-rendered episode into other languages: translated subtitle
   tracks + a dubbed .mp4 per language (cloned voices, fit to the original timing).
   Each language is a dub job on the render queue; we stream each job's dub.stage.*
   events for per-language progress, then surface download links. */
export function LocalizeModal({ slug, open, onClose }: { slug: string; open: boolean; onClose: () => void }) {
  const t = useT();
  const push = useStore((s) => s.pushToast);

  const info = useQuery({ queryKey: ["localize", slug], queryFn: () => localizeApi.get(slug), enabled: open });

  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [engine, setEngine] = useState("qwen");
  const [subsOnly, setSubsOnly] = useState(false);
  const [running, setRunning] = useState(false);
  const [langState, setLangState] = useState<Record<string, LangState>>({});
  const esRef = useRef<EventSource[]>([]);

  // Reset when (re)opened.
  useEffect(() => {
    if (open) {
      setPicked(new Set());
      setEngine("qwen");
      setSubsOnly(false);
      setRunning(false);
      setLangState({});
    }
  }, [open]);

  // Close all streams on unmount / close.
  useEffect(() => () => { esRef.current.forEach((e) => e.close()); esRef.current = []; }, []);

  const doneSet = useMemo(
    () => new Set((info.data?.languages ?? []).filter((l) => l.has_mp4 || l.has_srt).map((l) => l.code)),
    [info.data],
  );
  const langs = useMemo(() => LOCALES.filter((l) => l.code !== "en"), []);

  function toggle(code: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
  }

  function watch(jobs: LocalizeJob[]) {
    jobs.forEach((j) => {
      setLangState((s) => ({ ...s, [j.lang]: { step: "translate", status: "running" } }));
      const es = new EventSource(jobStreamUrl(j.job_id, 0));
      esRef.current.push(es);
      es.onmessage = (m) => {
        let ev: any;
        try { ev = JSON.parse(m.data); } catch { return; }
        setLangState((s) => {
          const cur = s[j.lang] || { step: "translate", status: "running" as const };
          if (ev.kind === "dub.stage.started") return { ...s, [j.lang]: { ...cur, step: ev.step } };
          if (ev.kind === "dub.progress" && ev.step === "vo")
            return { ...s, [j.lang]: { ...cur, step: "vo", voDone: ev.done, voTotal: ev.total } };
          if (ev.kind === "job.done") return { ...s, [j.lang]: { ...cur, status: "done" } };
          if (ev.kind === "job.error") return { ...s, [j.lang]: { ...cur, status: "error", error: ev.error } };
          return s;
        });
      };
      es.addEventListener("end", () => es.close());
      es.onerror = () => { /* SSE closes on end; transient errors retry automatically */ };
    });
  }

  async function start() {
    if (picked.size === 0) return;
    try {
      const r = await localizeApi.run(slug, { languages: [...picked], engine, subs_only: subsOnly });
      setRunning(true);
      push(t("localize.queued", { n: r.jobs.length }), "run");
      watch(r.jobs);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      push(msg.toLowerCase().includes("409") ? t("localize.busyOrUnrendered") : t("localize.startFailed", { msg }), "err");
    }
  }

  if (!open) return null;
  const rendered = info.data?.rendered ?? true;
  const engines = info.data?.engines ?? [];

  return (
    <Modal
      open
      onClose={onClose}
      title={t("localize.title")}
      width={640}
      footer={
        running ? (
          <button className="btn btn-amber" onClick={onClose}>{t("common.close")}</button>
        ) : (
          <>
            <button className="btn" onClick={onClose}>{t("common.close")}</button>
            <button className="btn btn-amber" disabled={!rendered || picked.size === 0} onClick={start}>
              {subsOnly ? t("localize.startSubs", { n: picked.size }) : t("localize.startDub", { n: picked.size })}
            </button>
          </>
        )
      }
    >
      {!rendered ? (
        <p className="label-tiny text-amber leading-relaxed py-4">{t("localize.renderFirst")}</p>
      ) : running ? (
        /* ---- per-language progress ---- */
        <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto">
          <p className="label-tiny opacity-70 leading-relaxed">{t("localize.runningNote")}</p>
          {[...picked].map((code) => {
            const l = langs.find((x) => x.code === code);
            const st = langState[code];
            return (
              <div key={code} className="flex items-center gap-3 px-3 py-2 rounded hairline-soft">
                <span className="text-[12px] w-40 truncate">{l?.nativeName} <span className="label-tiny text-txt-dim">{l?.englishName}</span></span>
                <span className="flex-1 label-tiny">
                  {!st ? t("localize.queuedShort")
                    : st.status === "done" ? <span className="text-green">{t("localize.done")}</span>
                    : st.status === "error" ? <span className="text-err">{st.error || t("localize.failed")}</span>
                    : <span className="text-amber">{t(STEP_KEY[st.step] || "localize.step.translate")}{st.step === "vo" && st.voTotal ? ` ${st.voDone}/${st.voTotal}` : "…"}</span>}
                </span>
                {st?.status === "done" && (
                  <span className="flex gap-1.5">
                    {/* subs-only still burns a subtitled video (English audio + translated subs) */}
                    <a className="btn p-1 label-tiny" href={dubUrl.video(slug, code)} download>{t("localize.video")}</a>
                    <a className="btn p-1 label-tiny" href={dubUrl.srt(slug, code)} download>{t("localize.srt")}</a>
                  </span>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        /* ---- config ---- */
        <div className="flex flex-col gap-3">
          <div className="label-tiny">{t("localize.engineLabel")}</div>
          <div className="flex flex-col gap-1.5">
            {engines.map((e) => (
              <label key={e.id} className="flex items-start gap-2 text-[12px] cursor-pointer">
                <input type="radio" name="loc-engine" className="mt-1" checked={engine === e.id} onChange={() => setEngine(e.id)} />
                <span><span className="text-amber font-semibold">{e.id}</span> — <span className="text-txt-dim">{e.caveat}</span></span>
              </label>
            ))}
          </div>
          <p className="label-tiny opacity-60 leading-relaxed">{t("localize.haikuNote")}</p>

          <label className="flex items-center gap-2 text-[12px] cursor-pointer select-none pt-1 border-t hairline-soft">
            <input type="checkbox" checked={subsOnly} onChange={(e) => setSubsOnly(e.target.checked)} />
            {t("localize.subsOnly")}
          </label>

          <div className="label-tiny pt-1 border-t hairline-soft">{t("localize.languagesLabel")}</div>
          <div className="grid grid-cols-2 gap-1 max-h-[260px] overflow-y-auto pr-1">
            {langs.map((l) => {
              const on = picked.has(l.code);
              const already = doneSet.has(l.code);
              return (
                <button key={l.code} onClick={() => toggle(l.code)}
                  className={"flex items-center gap-2 px-2 py-1.5 rounded text-left text-[12px] " + (on ? "btn-amber" : "hover:bg-bg-3")}>
                  <input type="checkbox" readOnly checked={on} className="pointer-events-none" />
                  <span className="truncate">{l.nativeName}</span>
                  <span className="label-tiny text-txt-dim truncate">{l.englishName}</span>
                  {already && <span className="label-tiny text-green ml-auto">✓</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </Modal>
  );
}
