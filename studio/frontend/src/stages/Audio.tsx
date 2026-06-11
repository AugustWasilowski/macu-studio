import { Fragment, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api, mediaUrl, jobStreamUrl } from "../api";
import { libraryApi } from "../api/library";
import { useStore } from "../store";
import { Badge } from "../components/Badge";
import { Waveform } from "../components/Waveform";
import { PlayBtn } from "../components/PlayBtn";
import { RegenNotes } from "../components/RegenNotes";
import { VersionArrows } from "../components/VersionArrows";
import { IRegen, IPlay, IPause, IDL } from "../components/Icons";
import { precacheMedia, isCached } from "../mediaCache";
import { useSfx, usePreview, GapZone, Library, PlayItem } from "./AudioSfx";
import { SfxGenModal } from "./SfxGenModal";
import { CreateVoiceModal } from "./CreateVoiceModal";
import { VoicePicker } from "./VoicePicker";
import { useCuePlayback } from "./useCuePlayback";
import type { Cue, PipelineEvent } from "../types";
import { useT } from "../i18n";

interface SpeakerInfo {
  color: string;
  engine?: string;
  profile_id?: string | null;
  voice_name?: string | null;
}

/* Deterministic color per speaker so the UI stays consistent across stages. */
function colorForSpeaker(name: string): string {
  if (!name) return "#938d82";
  const palette = ["#f5a623", "#00e5ff", "#33ff66", "#c08bff", "#ff7a59", "#9ad6ff", "#ffd166", "#7cc97a"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return palette[Math.abs(h) % palette.length];
}

export function Audio({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const busy = useStore((s) => s.busy);
  const setBusy = useStore((s) => s.setBusy);
  const selectedCueId = useStore((s) => s.selectedCueId);
  const selectCue = useStore((s) => s.selectCue);

  const cues = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug), refetchInterval: 4000 });
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });

  const sfx = useSfx(slug);
  const preview = usePreview();
  const [sfxGenOpen, setSfxGenOpen] = useState(false);
  const [createVoiceOpen, setCreateVoiceOpen] = useState(false);
  const [voicesOpen, setVoicesOpen] = useState(false);

  // Per-cue version-preview override URL (null = canonical cue audio).
  const [cueOverrides, setCueOverrides] = useState<Record<string, string | null>>({});
  const setCueOverride = (id: string, u: string | null) => setCueOverrides((s) => ({ ...s, [id]: u }));
  const overridesRef = useRef(cueOverrides);
  overridesRef.current = cueOverrides;

  // ---- playback: a queue of VO cues + interleaved SFX one-shots (shared engine) ----
  const playback = useCuePlayback({
    buildPlaylist: () => sfx.buildPlaylist(),
    resolveSingle: (cueId): PlayItem => {
      const c = cues.data?.cues.find((x) => x.id === cueId);
      const url = overridesRef.current[cueId] || mediaUrl.cueAudio(slug, cueId, c?.wav_mtime);
      return { url, cueId, label: cueId };
    },
    onCueChange: selectCue,
    notify: push,
  });
  const { continuous, setContinuous, curCueId, sequentialPlaying, togglePlay, playAll } = playback;

  // ---- pre-cache all of this episode's audio into the in-browser blob cache ----
  // (manual, button-driven — sidesteps Cloudflare revalidation lag on playback)
  const [precaching, setPrecaching] = useState<{ done: number; total: number } | null>(null);
  const precache = async () => {
    if (precaching) return;
    const urls = sfx.precacheUrls();
    if (!urls.length) { push(t("toast.noAudioToCache"), "info"); return; }
    const need = urls.filter((u) => !isCached(u));
    if (!need.length) { push(t("toast.allClipsCached", { count: urls.length }), "ok"); return; }
    setPrecaching({ done: 0, total: need.length });
    push(t("toast.preCaching", { count: need.length }), "run");
    const r = await precacheMedia(urls, (p) => setPrecaching({ done: p.done, total: p.total }));
    setPrecaching(null);
    push(
      r.failed
        ? t("toast.audioCachedWithFailed", { done: r.done - r.failed, total: r.total, failed: r.failed })
        : t("toast.audioCached", { done: r.done - r.failed, total: r.total }),
      r.failed ? "err" : "ok",
    );
  };

  // Watch regen jobs for live status, but CAP concurrent EventSources. "Regen missing"
  // fires one render job per cue; one long-lived SSE stream each (28+) would exhaust the
  // browser's ~6-per-host HTTP/1.1 limit and starve the 4s cues poll — so finished cues
  // stayed red until a manual refresh. Jobs run serially in the render service, so a few
  // open streams is plenty; the rest queue and open as slots free (each replays from the
  // start, so a job that finished while queued is still caught).
  const MAX_WATCH = 3;
  const watchQ = useRef<Array<{ jobId: string; cueId: string }>>([]);
  const watchOpen = useRef(0);

  const pumpWatch = () => {
    while (watchOpen.current < MAX_WATCH && watchQ.current.length) {
      const { jobId, cueId } = watchQ.current.shift()!;
      watchOpen.current++;
      const key = `cue:${cueId}`;
      let done = false;
      const es = new EventSource(jobStreamUrl(jobId));
      const release = () => { if (done) return; done = true; es.close(); watchOpen.current--; pumpWatch(); };
      es.onmessage = (m) => {
        let ev: PipelineEvent;
        try { ev = JSON.parse(m.data); } catch { return; }
        if (ev.kind === "stage.done" || ev.kind === "job.done") {
          setBusy(key, false);
          qc.invalidateQueries({ queryKey: ["cues", slug] });
          qc.invalidateQueries({ queryKey: ["versions", "cue", slug, cueId] });
          push(t("toast.voRegenerated", { cueId }), "ok");
          release();
        } else if (ev.kind === "stage.error" || ev.kind === "job.error") {
          setBusy(key, false);
          push(t("toast.voRegenFailed", { cueId, error: ev.error }), "err");
          release();
        }
      };
      es.addEventListener("end", release);
    }
  };

  const watchJob = (jobId: string, cueId: string) => {
    setBusy(`cue:${cueId}`, true);
    watchQ.current.push({ jobId, cueId });
    pumpWatch();
  };

  const regen = useMutation({
    mutationFn: (cueId: string) => api.regenCue(slug, cueId),
    onMutate: (cueId) => { setBusy(`cue:${cueId}`, true); push(t("toast.voCuePipeline", { cueId }), "run"); },
    onSuccess: (r, cueId) => watchJob(r.job_id, cueId),
    onError: (e: Error, cueId) => { setBusy(`cue:${cueId}`, false); push(t("toast.regenFailed", { message: e.message }), "err"); },
  });

  // Edit a cue's VO text (the line the TTS reads) and save the manifest, like the script editor.
  const saveCueText = useMutation({
    mutationFn: async ({ id, text }: { id: string; text: string }) => {
      const m = manifest.data as any;
      if (!m) throw new Error("manifest not loaded");
      const copy = JSON.parse(JSON.stringify(m));
      const cue = (copy.cues || []).find((c: any) => c.id === id);
      if (!cue) throw new Error(`cue ${id} not found`);
      if ((cue.vo || "") === text) return { noop: true };
      cue.vo = text;
      await api.putManifest(slug, copy);
      return { saved: true };
    },
    onSuccess: (r: any) => {
      if (r?.saved) {
        qc.invalidateQueries({ queryKey: ["manifest", slug] });
        qc.invalidateQueries({ queryKey: ["cues", slug] });
        push(t("toast.voTextSaved"), "ok");
      }
    },
    onError: (e: Error) => push(t("toast.saveFailed", { msg: e.message }), "err"),
  });

  const regenAllMissing = () => {
    const missing = cues.data?.cues.filter((c) => c.status === "missing") ?? [];
    if (!missing.length) { push(t("toast.noMissingVo"), "info"); return; }
    push(t("toast.queuingRegens", { count: missing.length }), "run");
    missing.forEach((c, i) => setTimeout(() => regen.mutate(c.id), i * 250));
  };

  const speakerMap: Record<string, SpeakerInfo> = useMemo(() => {
    const m = manifest.data as any;
    const map = (m?.voice?.speaker_map ?? {}) as Record<string, any>;
    const out: Record<string, SpeakerInfo> = {};
    Object.keys(map).forEach((k) => {
      out[k] = { color: colorForSpeaker(k), engine: map[k]?.engine, profile_id: map[k]?.profile_id, voice_name: map[k]?.voice_name };
    });
    return out;
  }, [manifest.data]);

  const cueList = cues.data?.cues ?? [];
  const genCount = cueList.filter((c) => c.status === "generated").length;
  const totalRuntime = cueList.reduce((a, c) => a + (c.duration_s ?? 0), 0);
  const selCue = selectedCueId ? cueList.find((c) => c.id === selectedCueId) : null;

  // a full-width table row holding the SFX dropzone for the gap after `afterId` (null = before first cue)
  const gapRow = (afterId: string | null) => (
    <tr key={`gap:${afterId ?? "__head"}`}>
      <td colSpan={8} className="p-0">
        <GapZone
          entries={sfx.entriesByGap(afterId)}
          onDrop={() => sfx.onDropGap(afterId)}
          onDelete={sfx.del}
          onGain={sfx.setGain}
          onDelay={sfx.setDelay}
          onPlay={(file) => preview.toggle(libraryApi.audioUrl("sfx", file))}
          previewUrl={preview.previewUrl}
        />
      </td>
    </tr>
  );

  return (
    <div className="grid grid-cols-[1fr_368px] gap-3 h-full min-h-0">
      <div className="flex flex-col gap-3 min-h-0">
        {/* VOICEOVER + interleaved SFX */}
        <section className="panel flex flex-col min-h-0">
          <header className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">{t("audio.sectionTitle")} <span className="text-txt-faint">{t("audio.sectionSubtitle")}</span></div>
            <div className="flex items-center gap-2">
              <span className="seg-readout">{String(genCount).padStart(2, "0")}<span className="text-txt-faint">/{cueList.length}</span> {t("audio.cuesLabel")}</span>
              <button className="btn btn-cyan" onClick={playAll} title={sequentialPlaying ? t("audio.stopPlaybackTitle") : t("audio.playAllTitle")}>
                {sequentialPlaying ? <IPause /> : <IPlay />} {sequentialPlaying ? t("audio.stop") : t("audio.playAll")}
              </button>
              <label className="flex items-center gap-1 text-[11px] text-txt-dim cursor-pointer select-none" title={t("audio.continuousTitle")}>
                <input type="checkbox" checked={continuous} onChange={(e) => setContinuous(e.target.checked)} />
                {t("audio.continuous")}
              </label>
              <button className="btn btn-amber" onClick={regenAllMissing}><IRegen /> {t("audio.regenMissing")}</button>
              <button className="btn btn-cyan" onClick={() => setSfxGenOpen(true)}
                title={t("audio.generateSfxTitle")}>
                <IRegen /> {t("audio.generateSfx")}
              </button>
              <button className={"btn " + (voicesOpen ? "btn-amber" : "")} onClick={() => setVoicesOpen((v) => !v)}
                title={t("audio.voicesTitle")}>
                {t("audio.voices")}
              </button>
              <button className="btn" onClick={() => setCreateVoiceOpen(true)}
                title={t("audio.createVoiceTitle")}>
                {t("audio.createVoice")}
              </button>
              <button
                className="btn"
                onClick={precache}
                disabled={!!precaching}
                title={t("audio.preCacheTitle")}
              >
                <IDL /> {precaching ? t("audio.caching", { done: precaching.done, total: precaching.total }) : t("audio.preCacheAudio")}
              </button>
            </div>
          </header>
          {voicesOpen && <VoicePicker slug={slug} />}
          <div className="overflow-y-auto flex-1">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-bg-1">
                <tr className="label-tiny text-left border-b hairline-soft">
                  <th className="px-2 py-1">{t("audio.colCue")}</th>
                  <th className="px-2 py-1">{t("audio.colSpeaker")}</th>
                  <th className="px-2 py-1">{t("audio.colVoText")}</th>
                  <th className="px-2 py-1">{t("audio.colWave")}</th>
                  <th className="px-2 py-1">{t("audio.colDur")}</th>
                  <th className="px-2 py-1">{t("audio.colStatus")}</th>
                  <th className="px-2 py-1"></th>
                  <th className="px-2 py-1">{t("audio.colVer")}</th>
                </tr>
              </thead>
              <tbody>
                {gapRow(null)}
                {cueList.map((c) => {
                  const isPlaying = curCueId === c.id;
                  const isBusy = busy[`cue:${c.id}`];
                  const active = selectedCueId === c.id;
                  const spk = speakerMap[c.speaker] ?? { color: colorForSpeaker(c.speaker) };
                  return (
                    <Fragment key={c.id}>
                      <tr
                        onClick={() => selectCue(c.id)}
                        className={"border-b border-[var(--line-soft)] hover:bg-bg-3 cursor-pointer " + (active ? "bg-bg-3" : "")}
                      >
                        <td className="px-2 py-1.5 text-amber font-bold">{c.id}</td>
                        <td className="px-2 py-1.5 whitespace-nowrap">
                          <span className="inline-flex items-center gap-1.5" style={{ color: spk.color }}>
                            <span className="led-dot" style={{ "--led-c": spk.color } as React.CSSProperties} />
                            {c.speaker}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 max-w-[400px] truncate" title={c.text}>
                          {c.is_hold ? <span className="text-txt-faint italic">{t("audio.holdLabel", { seconds: c.hold_seconds })}</span> : c.text}
                        </td>
                        <td className="px-2 py-1.5">
                          <Waveform seed={(parseInt(c.id.replace(/\D/g, ""), 10) || 1) + 7} w={120} h={26} playing={isPlaying} dense={70} />
                        </td>
                        <td className="px-2 py-1.5 text-cyan whitespace-nowrap">{c.duration_s != null ? `${c.duration_s.toFixed(1)}s` : "—"}</td>
                        <td className="px-2 py-1.5"><Badge status={isBusy ? "running" : c.status} /></td>
                        <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-1">
                            <PlayBtn playing={isPlaying} onClick={() => togglePlay(c.id)} title={c.wav_exists ? t("audio.play") : t("audio.noWavYet")} />
                            <button className="btn p-1" title={t("audio.regenerate")} disabled={isBusy} onClick={() => regen.mutate(c.id)}><IRegen /></button>
                            <RegenNotes onSubmit={(_) => regen.mutate(c.id)} />
                          </div>
                        </td>
                        <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                          <VersionArrows slug={slug} kind="cue" vkey={c.id}
                            onView={(u) => setCueOverride(c.id, u)}
                            onChanged={() => qc.invalidateQueries({ queryKey: ["cues", slug] })} />
                        </td>
                      </tr>
                      {gapRow(c.id)}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            {cueList.length === 0 && <div className="p-4 text-txt-faint">{t("audio.noCues")}</div>}
          </div>
        </section>
      </div>

      {/* Right column: inspector (top) + library (bottom) */}
      <aside className="flex flex-col gap-3 min-h-0">
        <div className="panel p-3 flex flex-col gap-3 overflow-y-auto" style={{ maxHeight: "55%" }}>
          <div className="panel-title">{t("audio.manifestPreview")}</div>
          {selCue ? (
            <CueInspector
              key={selCue.id}
              cue={selCue}
              isPlaying={curCueId === selCue.id}
              isBusy={!!busy[`cue:${selCue.id}`]}
              speaker={speakerMap[selCue.speaker] ?? { color: colorForSpeaker(selCue.speaker) }}
              slug={slug}
              onPlay={() => togglePlay(selCue.id)}
              onRegen={() => regen.mutate(selCue.id)}
              onSaveText={(text) => saveCueText.mutate({ id: selCue.id, text })}
            />
          ) : (
            <div className="text-txt-faint">{t("audio.selectCueHint")}</div>
          )}
        </div>
        <Library slug={slug} previewUrl={preview.previewUrl} onPreview={preview.toggle} />
      </aside>
      <SfxGenModal slug={slug} open={sfxGenOpen} onClose={() => setSfxGenOpen(false)} />
      <CreateVoiceModal open={createVoiceOpen} onClose={() => setCreateVoiceOpen(false)} />
    </div>
  );
}

function CueInspector({
  cue, isPlaying, isBusy, speaker, slug, onPlay, onRegen, onSaveText,
}: {
  cue: Cue;
  isPlaying: boolean;
  isBusy: boolean;
  speaker: SpeakerInfo;
  slug: string;
  onPlay: () => void;
  onRegen: () => void;
  onSaveText: (text: string) => void;
}) {
  const t = useT();
  void slug;
  // Local draft; the component is keyed by cue.id so this resets when you select another cue.
  const [draft, setDraft] = useState(cue.text);
  const saveIfChanged = () => { if (draft !== cue.text) onSaveText(draft); };
  return (
    <>
      <div className="flex items-center gap-3">
        <span className="text-amber font-bold text-2xl">{cue.id}</span>
        <span className="inline-flex items-center gap-1.5" style={{ color: speaker.color }}>
          <span className="led-dot" style={{ "--led-c": speaker.color } as React.CSSProperties} />
          {cue.speaker}
        </span>
        <Badge status={isBusy ? "running" : cue.status} />
      </div>
      <div className="bg-[var(--logtail-bg)] hairline-soft p-2 rounded">
        <Waveform seed={(parseInt(cue.id.replace(/\D/g, ""), 10) || 1) + 7} w={320} h={72} playing={isPlaying} dense={160} />
      </div>
      <div className="flex items-center gap-2">
        <PlayBtn playing={isPlaying} onClick={onPlay} />
        <button className="btn" onClick={onRegen} disabled={isBusy}><IRegen /> {t("audio.regen")}</button>
        <RegenNotes onSubmit={() => onRegen()} />
      </div>
      <div className="flex flex-col gap-1">
        <span className="label-tiny">cue.text <span className="text-txt-faint">{t("audio.cueTextHint")}</span></span>
        <textarea
          className="input w-full text-amber"
          style={{ minHeight: 80, resize: "vertical", whiteSpace: "pre-wrap" }}
          value={draft}
          placeholder={cue.is_hold ? t("audio.holdPlaceholder") : t("audio.voPlaceholder")}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={saveIfChanged}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); }
          }}
        />
      </div>
      <div className="grid grid-cols-2 gap-1.5 text-[12px]">
        <span className="label-tiny">speaker</span><span>{cue.speaker}</span>
        <span className="label-tiny">engine</span><span>{cue.engine ?? "—"}</span>
        <span className="label-tiny">profile_id</span><span className="break-all">{cue.profile_id ?? "—"}</span>
        <span className="label-tiny">voice_name</span><span>{cue.voice_name ?? "—"}</span>
        <span className="label-tiny">duration</span><span className="text-cyan">{cue.duration_s != null ? `${cue.duration_s.toFixed(2)}s` : "—"}</span>
        <span className="label-tiny">segment</span><span>{cue.segment ?? "—"}</span>
        <span className="label-tiny">file</span><span className="break-all">vo/{cue.id}.wav</span>
        <span className="label-tiny">shots</span><span>{cue.shots.length}</span>
      </div>
    </>
  );
}
