import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, jobStreamUrl, mediaUrl } from "../api";
import { useStore } from "../store";
import { Badge } from "../components/Badge";
import { PlayBtn } from "../components/PlayBtn";
import { RegenNotes } from "../components/RegenNotes";
import { Modal } from "../components/Modal";
import { Field } from "../components/Field";
import { VersionArrows } from "../components/VersionArrows";
import { IRegen, IPlus, IDL } from "../components/Icons";
import { precacheMedia, resolveMedia, isCached } from "../mediaCache";
import { versionsApi } from "../api/assets";
import { ShotGenModal } from "./ShotGenModal";
import { useT } from "../i18n";
import type { PipelineEvent, Shot } from "../types";

// The Video tab is the shot list. (The timeline moved to the Assembly tab.)
export function Video({ slug }: { slug: string }) {
  return <ShotsView slug={slug} />;
}

function ShotsView({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const busy = useStore((s) => s.busy);
  const setBusy = useStore((s) => s.setBusy);
  const selectedKey = useStore((s) => s.selectedShotKey);
  const selectShot = useStore((s) => s.selectShot);

  const shots = useQuery({
    queryKey: ["shots", slug],
    queryFn: () => api.shots(slug),
    refetchInterval: 4000, // self-refresh so renders show up without navigating away
  });
  const manifest = useQuery({
    queryKey: ["manifest", slug],
    queryFn: () => api.manifest(slug),
  });

  const [draftPrompt, setDraftPrompt] = useState<string | null>(null);
  const [draftSeed, setDraftSeed] = useState<Record<string, number | null>>({});
  // Per-shot version-preview override URL (null = canonical shot preview).
  const [shotOverrides, setShotOverrides] = useState<Record<string, string | null>>({});
  const setShotOverride = (key: string, u: string | null) =>
    setShotOverrides((s) => ({ ...s, [key]: u }));
  // Per-shot seed shown while browsing a history version (undefined = live →
  // fall back to the manifest seed; null = that version recorded no seed).
  const [viewSeeds, setViewSeeds] = useState<Record<string, number | null | undefined>>({});
  const setViewSeed = (key: string, seed: number | null | undefined) =>
    setViewSeeds((s) => ({ ...s, [key]: seed }));
  const [addOpen, setAddOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);

  // Cap concurrent watch streams (see Audio.tsx): "render all missing" fires a render
  // and would otherwise open one SSE stream per shot, exhausting the ~6-per-host HTTP/1.1
  // limit and starving the shots poll. Queue them; ≤3 open at once (each replays from the
  // start, so a job already done while queued is still caught).
  const MAX_WATCH = 3;
  const watchQ = useRef<Array<{ jobId: string; key: string }>>([]);
  const watchOpen = useRef(0);

  const pumpWatch = () => {
    while (watchOpen.current < MAX_WATCH && watchQ.current.length) {
      const { jobId, key } = watchQ.current.shift()!;
      watchOpen.current++;
      let done = false;
      const es = new EventSource(jobStreamUrl(jobId));
      const release = () => { if (done) return; done = true; es.close(); watchOpen.current--; pumpWatch(); };
      es.onmessage = (m) => {
        let ev: PipelineEvent;
        try { ev = JSON.parse(m.data); } catch { return; }
        if (ev.kind === "job.done") {
          setBusy(`shot:${key}`, false);
          push(t("toast.shotRendered", { key }), "ok");
          qc.invalidateQueries({ queryKey: ["shots", slug] });
          qc.invalidateQueries({ queryKey: ["versions", "shot", slug, key] });
          release();
        } else if (ev.kind === "job.error" || ev.kind === "stage.error") {
          setBusy(`shot:${key}`, false);
          push(t("toast.shotFailed", { key, error: ev.error }), "err");
          release();
        }
      };
      es.addEventListener("end", release);
    }
  };

  const watchJob = (jobId: string, key: string) => {
    setBusy(`shot:${key}`, true);
    watchQ.current.push({ jobId, key });
    pumpWatch();
  };

  const regen = useMutation({
    mutationFn: (key: string) => api.regenShot(slug, key),
    onMutate: (key) => {
      setBusy(`shot:${key}`, true);
      setShotOverride(key, null);
      setViewSeed(key, undefined);
      push(t("toast.shotQueued", { key }), "run");
    },
    onSuccess: (r, key) => watchJob(r.job_id, key),
    onError: (e: Error, key) => { setBusy(`shot:${key}`, false); push(`regen failed: ${e.message}`, "err"); },
  });

  const saveSeed = useMutation({
    mutationFn: async ({ key, kind, seed }: { key: string; kind: "character" | "broll"; seed: number }) => {
      if (!manifest.data) throw new Error("manifest not loaded yet");
      const m = JSON.parse(JSON.stringify(manifest.data));
      if (kind === "character" && m.characters?.[key]) {
        m.characters[key].seed = seed;
      } else if (kind === "broll" && m.broll?.[key]) {
        if (typeof m.broll[key] === "string") {
          m.broll[key] = { prompt: m.broll[key], seed };
        } else m.broll[key].seed = seed;
      }
      return api.putManifest(slug, m);
    },
    onSuccess: (_r, vars) => {
      push(t("toast.seedUpdated", { key: vars.key }), "ok");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["shots", slug] });
      setDraftSeed((s) => ({ ...s, [vars.key]: null }));
    },
    onError: (e: Error) => push("save failed: " + e.message, "err"),
  });

  const savePrompt = useMutation({
    mutationFn: async ({ key, kind, prompt }: { key: string; kind: "character" | "broll"; prompt: string }) => {
      if (!manifest.data) throw new Error("manifest not loaded yet");
      const m = JSON.parse(JSON.stringify(manifest.data));
      if (kind === "character") {
        if (m.characters?.[key]) m.characters[key].core = prompt;
      } else {
        if (m.broll?.[key] !== undefined) {
          if (typeof m.broll[key] === "string") m.broll[key] = prompt;
          else m.broll[key].prompt = prompt;
        }
      }
      return api.putManifest(slug, m);
    },
    onSuccess: () => {
      push(t("toast.promptWritten"), "ok");
      setDraftPrompt(null);
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["shots", slug] });
    },
    onError: (e: Error) => push("save failed: " + e.message, "err"),
  });

  const renderAllMissing = () => {
    const ss = shots.data?.shots ?? [];
    const m = ss.filter((s) => s.status === "missing" || s.status === "stale");
    if (!m.length) { push(t("toast.nothingToRender"), "info"); return; }
    push(t("toast.queuingShots", { count: m.length }), "run");
    // The regen helper hits from_stage=2 anyway; one job covers all missing/stale.
    api.run(slug, { from_stage: 2 }).then((r) => {
      m.forEach((s) => watchJob(r.job_id, s.key));
    }).catch((e) => push("queue failed: " + e.message, "err"));
  };

  // ---- pre-cache all rendered shot masters into the in-browser blob cache ----
  // (manual, button-driven — sidesteps Cloudflare revalidation lag on preview)
  const [precaching, setPrecaching] = useState<{ done: number; total: number } | null>(null);
  const precache = async () => {
    if (precaching) return;
    const urls = (shots.data?.shots ?? [])
      .filter((s) => s.webp_exists)
      .map((s) => mediaUrl.shotPreview(slug, s.key, s.webp_mtime));
    if (!urls.length) { push(t("toast.noMastersToCache"), "info"); return; }
    const need = urls.filter((u) => !isCached(u));
    if (!need.length) { push(t("toast.allMastersCached", { count: urls.length }), "ok"); return; }
    setPrecaching({ done: 0, total: need.length });
    push(t("toast.precachingMasters", { count: need.length }), "run");
    const r = await precacheMedia(urls, (p) => setPrecaching({ done: p.done, total: p.total }));
    setPrecaching(null);
    push(
      r.failed
        ? t("toast.videoCachedWithErrors", { done: r.done - r.failed, total: r.total, failed: r.failed })
        : t("toast.videoCached", { done: r.done - r.failed, total: r.total }),
      r.failed ? "err" : "ok",
    );
  };

  const list = shots.data?.shots ?? [];
  const renderedCount = list.filter((s) => s.status === "rendered").length;
  const cur = useMemo(() => list.find((s) => s.key === selectedKey) ?? list[0], [list, selectedKey]);

  // Auto-select first shot once we have data
  useEffect(() => {
    if (!selectedKey && list.length > 0) selectShot(list[0].key);
  }, [list, selectedKey, selectShot]);

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      <div className="grid grid-cols-[1fr_380px] gap-3 flex-1 min-h-0">
      <section className="panel flex flex-col min-h-0">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">{t("video.shotListTitle")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {t("video.shotListSub")}</span></div>
          <div className="flex items-center gap-2">
            <span className="seg-readout">{renderedCount}<span className="text-txt-faint">/{list.length}</span> {t("video.rendered")}</span>
            <button className="btn btn-cyan" onClick={() => setGenOpen(true)} title={t("video.generateShotListTitle")}>
              <IRegen /> {t("video.generateShotList")}
            </button>
            <button className="btn btn-cyan" onClick={() => setAddOpen(true)}>
              <IPlus /> {t("video.addShot")}
            </button>
            <button className="btn btn-amber" onClick={renderAllMissing}>
              <IRegen /> {t("video.renderAllMissing")}
            </button>
            <button
              className="btn"
              onClick={precache}
              disabled={!!precaching}
              title={t("video.precacheTitle")}
            >
              <IDL /> {precaching ? t("video.caching", { done: precaching.done, total: precaching.total }) : t("video.precacheVideo")}
            </button>
          </div>
        </header>
        <div className="overflow-y-auto flex-1">
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-bg-1">
              <tr className="label-tiny text-left border-b hairline-soft">
                <th className="px-2 py-1">{t("video.colShot")}</th>
                <th className="px-2 py-1">{t("video.colKind")}</th>
                <th className="px-2 py-1">{t("video.colPrompt")}</th>
                <th className="px-2 py-1 w-[90px]">{t("video.colSeed")}</th>
                <th className="px-2 py-1">{t("video.colStatus")}</th>
                <th className="px-2 py-1"></th>
                <th className="px-2 py-1">{t("video.colVer")}</th>
              </tr>
            </thead>
            <tbody>
              {list.map((s) => {
                const k = `shot:${s.key}`;
                const isBusy = !!busy[k];
                const active = selectedKey === s.key;
                const seed = draftSeed[s.key] ?? s.seed ?? 0;
                const dirty = draftSeed[s.key] != null && draftSeed[s.key] !== s.seed;
                const vseed = viewSeeds[s.key];
                const viewingVersion = vseed !== undefined;
                return (
                  <tr
                    key={`${s.kind}/${s.key}`}
                    onClick={() => { selectShot(s.key); setDraftPrompt(null); }}
                    className={"border-b border-[var(--line-soft)] hover:bg-bg-3 cursor-pointer " + (active ? "bg-bg-3" : "")}
                  >
                    <td className="px-2 py-1.5">
                      <span className="font-mono inline-flex items-center gap-1.5">
                        {s.kind === "character" ? (
                          <span className="led-dot" style={{ "--led-c": "#f5a623" } as React.CSSProperties} />
                        ) : (
                          <span className="text-cyan font-bold border border-cyan/40 px-1 rounded text-[10px]">B</span>
                        )}
                        {s.key}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-txt-faint">{s.kind}</td>
                    <td className="px-2 py-1.5 max-w-[440px] truncate" title={s.prompt}>{s.prompt}</td>
                    <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                      <input
                        className="input font-mono w-full"
                        style={{ height: 24, padding: "0 4px", ...(viewingVersion ? { opacity: 0.6 } : {}) }}
                        value={viewingVersion ? (vseed ?? "") : seed}
                        placeholder={viewingVersion ? "—" : undefined}
                        readOnly={viewingVersion}
                        title={viewingVersion ? t("video.seedVersionReadOnly") : undefined}
                        onChange={(e) => {
                          if (viewingVersion) return;
                          const v = parseInt(e.target.value.replace(/\D/g, ""), 10) || 0;
                          setDraftSeed((d) => ({ ...d, [s.key]: v }));
                        }}
                        onBlur={() => {
                          if (!viewingVersion && dirty) saveSeed.mutate({ key: s.key, kind: s.kind, seed });
                        }}
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <Badge status={isBusy ? "running" : (dirty ? "stale" : s.status)} />
                    </td>
                    <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <button
                          className="btn p-1"
                          title={t("video.regenTitle")}
                          disabled={isBusy}
                          onClick={() => regen.mutate(s.key)}
                        ><IRegen /></button>
                        <RegenNotes onSubmit={() => regen.mutate(s.key)} />
                      </div>
                    </td>
                    <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                      <VersionArrows
                        slug={slug}
                        kind="shot"
                        vkey={s.key}
                        onView={(u, vs) => {
                          setShotOverride(s.key, u);
                          setViewSeed(s.key, u == null ? undefined : (vs ?? null));
                        }}
                        onChanged={() => {
                          setViewSeed(s.key, undefined);
                          qc.invalidateQueries({ queryKey: ["shots", slug] });
                        }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {list.length === 0 && <div className="p-3 text-txt-faint">{t("video.emptyManifest")}</div>}
        </div>
      </section>

      <aside className="panel p-3 flex flex-col gap-3 overflow-y-auto">
        <div className="flex items-center justify-between">
          <div className="panel-title">{t("video.preview")}</div>
          {cur && <Badge status={busy[`shot:${cur.key}`] ? "running" : cur.status} />}
        </div>
        {cur ? (
          <>
            {(shotOverrides[cur.key] || cur.webp_exists) ? (
              <img
                key={(shotOverrides[cur.key] || mediaUrl.shotPreview(slug, cur.key)) + (cur.webp_mtime ?? "")}
                src={shotOverrides[cur.key] || resolveMedia(mediaUrl.shotPreview(slug, cur.key, cur.webp_mtime))}
                alt={cur.key}
                className="w-full hairline-soft bg-black"
                style={{ aspectRatio: "1/1", objectFit: "contain" }}
              />
            ) : (
              <MediaPlaceholder label={`${cur.key}_master.zs.webp`} status={cur.status} />
            )}
            <div className="flex items-center gap-2">
              <PlayBtn playing={false} onClick={() => { /* webp animates itself */ }} />
              <button className="btn" disabled={!!busy[`shot:${cur.key}`]} onClick={() => regen.mutate(cur.key)}>
                <IRegen /> {t("video.regen")}
              </button>
              <RegenNotes onSubmit={() => regen.mutate(cur.key)} />
            </div>
            <div className="grid grid-cols-2 gap-1 text-[12px]">
              <span className="label-tiny">{t("video.detailKey")}</span><span className="font-mono">{cur.key}</span>
              <span className="label-tiny">{t("video.detailKind")}</span><span>{cur.kind}</span>
              <span className="label-tiny">{t("video.detailSeed")}</span><span className="text-cyan">{viewSeeds[cur.key] !== undefined ? (viewSeeds[cur.key] ?? "—") : (cur.seed ?? "—")}</span>
              <span className="label-tiny">{t("video.detailFile")}</span><span className="break-all">clips/{cur.key}_master.zs.webp</span>
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between">
                <span className="label-tiny">{t("video.promptCore")}</span>
                <button
                  className="text-cyan text-[11px]"
                  onClick={() => setDraftPrompt(draftPrompt === null ? (cur.prompt ?? "") : null)}
                >{draftPrompt === null ? t("video.editPrompt") : t("common.cancel")}</button>
              </div>
              {draftPrompt === null ? (
                <p className="whitespace-pre-wrap">{cur.prompt}</p>
              ) : (
                <>
                  <textarea
                    className="input"
                    style={{ height: 96, resize: "vertical" }}
                    value={draftPrompt}
                    onChange={(e) => setDraftPrompt(e.target.value)}
                  />
                  <button
                    className="btn btn-amber mt-1"
                    onClick={() => savePrompt.mutate({ key: cur.key, kind: cur.kind, prompt: draftPrompt })}
                  >{t("video.saveToManifest")}</button>
                </>
              )}
            </div>
          </>
        ) : (
          <div className="text-txt-faint">{t("video.noShotSelected")}</div>
        )}
      </aside>

      <AddShotDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        slug={slug}
        onAdded={() => {
          qc.invalidateQueries({ queryKey: ["shots", slug] });
          qc.invalidateQueries({ queryKey: ["manifest", slug] });
        }}
      />
      <ShotGenModal slug={slug} open={genOpen} onClose={() => setGenOpen(false)} />
      </div>
    </div>
  );
}

function AddShotDialog({ open, onClose, slug, onAdded }: {
  open: boolean;
  onClose: () => void;
  slug: string;
  onAdded: () => void;
}) {
  const t = useT();
  const push = useStore((s) => s.pushToast);
  const cues = useQuery({
    queryKey: ["cues", slug],
    queryFn: () => api.cues(slug),
    enabled: open,
  });
  const cueIds = cues.data?.cues.map((c) => c.id) ?? [];

  const [key, setKey] = useState("");
  const [kind, setKind] = useState<"character" | "broll">("character");
  const [prompt, setPrompt] = useState("");
  const [seed, setSeed] = useState("");
  const [attach, setAttach] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      setKey(""); setKind("character"); setPrompt(""); setSeed(""); setAttach(""); setBusy(false);
    }
  }, [open]);

  const submit = async () => {
    if (!key.trim()) { push(t("video.keyRequired"), "err"); return; }
    setBusy(true);
    try {
      const seedNum = seed.trim() ? parseInt(seed.replace(/\D/g, ""), 10) : null;
      await versionsApi.addShot(slug, {
        key: key.trim(),
        kind,
        prompt,
        seed: Number.isNaN(seedNum as number) ? null : seedNum,
        attach_to_cue: attach || null,
      });
      push(t("toast.shotAdded", { key: key.trim() }), "ok");
      onAdded();
      onClose();
    } catch (e: any) {
      push("add failed: " + (e?.message ?? "error"), "err");
    }
    setBusy(false);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("video.addShotTitle")}
      width={520}
      footer={
        <>
          <button className="btn" onClick={onClose}>{t("common.close")}</button>
          <button className="btn btn-cyan" disabled={busy || !key.trim()} onClick={submit}>
            {busy ? t("video.adding") : t("video.addToManifest")}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-2 gap-2">
          <Field label={t("video.fieldKey")} value={key} onChange={setKey} placeholder={t("video.fieldKeyPlaceholder")} />
          <Field label={t("video.fieldKind")} value={kind} onChange={(v) => setKind(v as "character" | "broll")} options={["character", "broll"]} />
        </div>
        <Field label={t("video.fieldPrompt")} value={prompt} onChange={setPrompt} rows={4} placeholder={t("video.fieldPromptPlaceholder")} />
        <div className="grid grid-cols-2 gap-2">
          <Field label={t("video.fieldSeed")} value={seed} onChange={setSeed} type="number" />
          <Field
            label={t("video.fieldAttachToCue")}
            value={attach}
            onChange={setAttach}
            options={["", ...cueIds]}
          />
        </div>
        <div className="text-[11px] text-txt-faint">
          {attach
            ? t("video.addShotHelpWithCue", { kind, cue: attach })
            : t("video.addShotHelp", { kind })}
        </div>
      </div>
    </Modal>
  );
}

function MediaPlaceholder({ label, status }: { label: string; status: string }) {
  return (
    <div className="hairline-soft bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
      <div className="text-center">
        <Badge status={status} />
        <div className="label-tiny mt-2 break-all">{label}</div>
      </div>
    </div>
  );
}
