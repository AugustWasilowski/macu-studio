import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api, mediaUrl, jobStreamUrl } from "../api";
import { useStore } from "../store";
import { Badge } from "../components/Badge";
import { Waveform } from "../components/Waveform";
import { PlayBtn } from "../components/PlayBtn";
import { RegenNotes } from "../components/RegenNotes";
import { VersionArrows } from "../components/VersionArrows";
import { IRegen, IPlay, IPause } from "../components/Icons";
import { SfxSection } from "./AudioSfx";
import type { Cue, PipelineEvent } from "../types";

interface SpeakerInfo {
  color: string;
  engine?: string;
  profile_id?: string | null;
  voice_name?: string | null;
}

/* Deterministic color per speaker so the UI stays consistent across stages.
   We never had a speaker palette in the manifest — derive from the name. */
function colorForSpeaker(name: string): string {
  if (!name) return "#938d82";
  const palette = ["#f5a623", "#00e5ff", "#33ff66", "#c08bff", "#ff7a59", "#9ad6ff", "#ffd166", "#7cc97a"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return palette[Math.abs(h) % palette.length];
}

export function Audio({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const busy = useStore((s) => s.busy);
  const setBusy = useStore((s) => s.setBusy);
  const selectedCueId = useStore((s) => s.selectedCueId);
  const selectCue = useStore((s) => s.selectCue);

  const cues = useQuery({
    queryKey: ["cues", slug],
    queryFn: () => api.cues(slug),
  });
  const manifest = useQuery({
    queryKey: ["manifest", slug],
    queryFn: () => api.manifest(slug),
  });

  const [playing, setPlaying] = useState<string | null>(null);
  // "single" = play this one clip and stop; "sequential" = auto-advance to the next cue.
  const [playMode, setPlayMode] = useState<"single" | "sequential">("single");
  // When on (default), a per-row play button plays continuously from that clip onward;
  // when off, it plays just that one clip (oneshot).
  const [continuous, setContinuous] = useState(true);
  const playModeRef = useRef(playMode);
  playModeRef.current = playMode;
  const cueListRef = useRef<Cue[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Per-cue version-preview override URL (null = canonical cue audio).
  const [cueOverrides, setCueOverrides] = useState<Record<string, string | null>>({});
  const setCueOverride = (id: string, u: string | null) =>
    setCueOverrides((s) => ({ ...s, [id]: u }));
  const overridesRef = useRef(cueOverrides);
  overridesRef.current = cueOverrides;

  // Bind <audio> events for play/pause/end to drive `playing` state
  useEffect(() => {
    if (!playing || playing.split(":")[0] !== "cue") return;
    const cueId = playing.split(":")[1];
    const src = overridesRef.current[cueId] || mediaUrl.cueAudio(slug, cueId);
    const a = new window.Audio(src);
    audioRef.current = a;
    a.onended = () => {
      if (playModeRef.current === "sequential") {
        const list = cueListRef.current;
        const i = list.findIndex((c) => c.id === cueId);
        for (let j = i + 1; j < list.length; j++) {
          if (list[j].wav_exists) { setPlaying(`cue:${list[j].id}`); return; }
        }
      }
      setPlaying(null);
    };
    // Surface failures instead of silently resetting — MediaError codes:
    // 2 = NETWORK (connection/proxy), 4 = SRC_NOT_SUPPORTED (got HTML/redirect
    // instead of audio, e.g. a Cloudflare Access login bounce). Tells glitch from bug.
    a.onerror = () => {
      const code = a.error?.code;
      const why = code === 2 ? "network/connection"
        : code === 4 ? "bad response (auth redirect?) — try reloading"
        : code === 3 ? "decode error" : `error ${code ?? "?"}`;
      push(`audio ${cueId} failed: ${why}`, "err");
      setPlaying(null);
    };
    a.play().catch((e: any) => {
      push(`audio ${cueId} didn't start: ${e?.name || e?.message || "blocked"}`, "err");
      setPlaying(null);
    });
    return () => { a.pause(); audioRef.current = null; };
  }, [playing, slug]);

  // Follow the playing clip in the Manifest Preview pane (esp. during sequential play).
  useEffect(() => {
    if (playing && playing.startsWith("cue:")) selectCue(playing.slice(4));
  }, [playing, selectCue]);

  const togglePlay = (cueId: string) => {
    // Continuous (default): a row click plays from there onward; otherwise oneshot.
    setPlayMode(continuous ? "sequential" : "single");
    setPlaying((p) => (p === `cue:${cueId}` ? null : `cue:${cueId}`));
  };

  // active regen jobs we're watching → cue ids
  const jobsRef = useRef<Record<string, string>>({});

  const watchJob = (jobId: string, cueId: string) => {
    const key = `cue:${cueId}`;
    jobsRef.current[jobId] = cueId;
    setBusy(key, true);
    const es = new EventSource(jobStreamUrl(jobId));
    es.onmessage = (m) => {
      let ev: PipelineEvent;
      try { ev = JSON.parse(m.data); } catch { return; }
      if (ev.kind === "stage.done" || ev.kind === "job.done") {
        setBusy(key, false);
        qc.invalidateQueries({ queryKey: ["cues", slug] });
        push(`VO ${cueId} regenerated`, "ok");
        es.close();
      } else if (ev.kind === "stage.error" || ev.kind === "job.error") {
        setBusy(key, false);
        push(`VO ${cueId} regen failed: ${ev.error}`, "err");
        es.close();
      }
    };
    es.addEventListener("end", () => es.close());
  };

  const regen = useMutation({
    mutationFn: (cueId: string) => api.regenCue(slug, cueId),
    onMutate: (cueId) => {
      setBusy(`cue:${cueId}`, true);
      push(`VO cue ${cueId} → pipeline`, "run");
    },
    onSuccess: (r, cueId) => {
      watchJob(r.job_id, cueId);
    },
    onError: (e: Error, cueId) => {
      setBusy(`cue:${cueId}`, false);
      push(`regen failed: ${e.message}`, "err");
    },
  });

  const regenAllMissing = () => {
    const missing = cues.data?.cues.filter((c) => c.status === "missing") ?? [];
    if (!missing.length) { push("No missing VO cues", "info"); return; }
    push(`Queuing ${missing.length} VO regenerations`, "run");
    missing.forEach((c, i) => setTimeout(() => regen.mutate(c.id), i * 250));
  };

  // Build speaker map from the manifest for the inspector + dot colors
  const speakerMap: Record<string, SpeakerInfo> = useMemo(() => {
    const m = manifest.data as any;
    const map = (m?.voice?.speaker_map ?? {}) as Record<string, any>;
    const out: Record<string, SpeakerInfo> = {};
    Object.keys(map).forEach((k) => {
      out[k] = {
        color: colorForSpeaker(k),
        engine: map[k]?.engine,
        profile_id: map[k]?.profile_id,
        voice_name: map[k]?.voice_name,
      };
    });
    return out;
  }, [manifest.data]);

  const cueList = cues.data?.cues ?? [];
  cueListRef.current = cueList;
  const genCount = cueList.filter((c) => c.status === "generated").length;
  const totalRuntime = cueList.reduce((a, c) => a + (c.duration_s ?? 0), 0);
  const selCue = selectedCueId ? cueList.find((c) => c.id === selectedCueId) : null;
  const sequentialPlaying = !!playing && playMode === "sequential";

  const playAll = () => {
    if (sequentialPlaying) { setPlaying(null); return; } // toggle off
    const first = cueList.find((c) => c.wav_exists);
    if (!first) { push("No playable VO clips", "info"); return; }
    setPlayMode("sequential");
    setPlaying(`cue:${first.id}`);
  };

  return (
    <div className="grid grid-cols-[1fr_368px] gap-3 h-full min-h-0">
      <div className="flex flex-col gap-3 min-h-0">
        {/* VO panel */}
        <section className="panel flex flex-col min-h-0">
          <header className="flex items-center justify-between px-3 py-2 border-b hairline">
            <div className="panel-title">VOICEOVER <span className="text-txt-faint">/ per cue</span></div>
            <div className="flex items-center gap-2">
              <span className="seg-readout">
                {String(genCount).padStart(2, "0")}<span className="text-txt-faint">/{cueList.length}</span> CUES
              </span>
              <span className="seg-readout cyan">
                {totalRuntime.toFixed(1)}<span className="text-txt-faint">s</span> RUNTIME
              </span>
              <button className="btn btn-cyan" onClick={playAll} title={sequentialPlaying ? "Stop sequential playback" : "Play all cues in sequence"}>
                {sequentialPlaying ? <IPause /> : <IPlay />} {sequentialPlaying ? "Stop" : "Play all"}
              </button>
              <label className="flex items-center gap-1 text-[11px] text-txt-dim cursor-pointer select-none" title="Row play buttons continue to the next clip (off = play one clip only)">
                <input type="checkbox" checked={continuous} onChange={(e) => setContinuous(e.target.checked)} />
                Continuous
              </label>
              <button className="btn btn-amber" onClick={regenAllMissing}>
                <IRegen /> Regenerate all missing
              </button>
            </div>
          </header>
          <div className="overflow-y-auto flex-1">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-bg-1">
                <tr className="label-tiny text-left border-b hairline-soft">
                  <th className="px-2 py-1">CUE</th>
                  <th className="px-2 py-1">SPEAKER</th>
                  <th className="px-2 py-1">VO TEXT</th>
                  <th className="px-2 py-1">WAVE</th>
                  <th className="px-2 py-1">DUR</th>
                  <th className="px-2 py-1">STATUS</th>
                  <th className="px-2 py-1"></th>
                  <th className="px-2 py-1">VER</th>
                </tr>
              </thead>
              <tbody>
                {cueList.map((c) => {
                  const k = `cue:${c.id}`;
                  const isPlaying = playing === k;
                  const isBusy = busy[k];
                  const active = selectedCueId === c.id;
                  const spk = speakerMap[c.speaker] ?? { color: colorForSpeaker(c.speaker) };
                  return (
                    <tr
                      key={c.id}
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
                        {c.is_hold ? <span className="text-txt-faint italic">[HOLD {c.hold_seconds}s]</span> : c.text}
                      </td>
                      <td className="px-2 py-1.5">
                        <Waveform
                          seed={(parseInt(c.id.replace(/\D/g, ""), 10) || 1) + 7}
                          w={120}
                          h={26}
                          playing={isPlaying}
                          dense={70}
                        />
                      </td>
                      <td className="px-2 py-1.5 text-cyan whitespace-nowrap">
                        {c.duration_s != null ? `${c.duration_s.toFixed(1)}s` : "—"}
                      </td>
                      <td className="px-2 py-1.5">
                        <Badge status={isBusy ? "running" : c.status} />
                      </td>
                      <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <PlayBtn
                            playing={isPlaying}
                            onClick={() => togglePlay(c.id)}
                            title={c.wav_exists ? "Play" : "No wav yet"}
                          />
                          <button
                            className="btn p-1"
                            title="Regenerate"
                            disabled={isBusy}
                            onClick={() => regen.mutate(c.id)}
                          >
                            <IRegen />
                          </button>
                          <RegenNotes onSubmit={(_) => regen.mutate(c.id)} />
                        </div>
                      </td>
                      <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                        <VersionArrows
                          slug={slug}
                          kind="cue"
                          vkey={c.id}
                          onView={(u) => setCueOverride(c.id, u)}
                          onChanged={() => qc.invalidateQueries({ queryKey: ["cues", slug] })}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {cueList.length === 0 && (
              <div className="p-4 text-txt-faint">No cues in manifest yet.</div>
            )}
          </div>
        </section>

        {/* SFX timeline + library */}
        <SfxSection slug={slug} />
      </div>

      {/* Right inspector */}
      <aside className="panel p-3 flex flex-col gap-3 overflow-y-auto">
        <div className="panel-title">MANIFEST PREVIEW</div>
        {selCue ? (
          <CueInspector
            cue={selCue}
            isPlaying={playing === `cue:${selCue.id}`}
            isBusy={!!busy[`cue:${selCue.id}`]}
            speaker={speakerMap[selCue.speaker] ?? { color: colorForSpeaker(selCue.speaker) }}
            slug={slug}
            onPlay={() => togglePlay(selCue.id)}
            onRegen={() => regen.mutate(selCue.id)}
          />
        ) : (
          <div className="text-txt-faint">Select a cue on the left to see its full metadata.</div>
        )}
      </aside>
    </div>
  );
}

function CueInspector({
  cue, isPlaying, isBusy, speaker, slug, onPlay, onRegen,
}: {
  cue: Cue;
  isPlaying: boolean;
  isBusy: boolean;
  speaker: SpeakerInfo;
  slug: string;
  onPlay: () => void;
  onRegen: () => void;
}) {
  void slug;
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
      <div className="bg-[#050505] hairline-soft p-2 rounded">
        <Waveform
          seed={(parseInt(cue.id.replace(/\D/g, ""), 10) || 1) + 7}
          w={320}
          h={72}
          playing={isPlaying}
          dense={160}
        />
      </div>
      <div className="flex items-center gap-2">
        <PlayBtn playing={isPlaying} onClick={onPlay} />
        <button className="btn" onClick={onRegen} disabled={isBusy}>
          <IRegen /> Regen
        </button>
        <RegenNotes onSubmit={() => onRegen()} />
      </div>
      <div className="flex flex-col gap-1">
        <span className="label-tiny">cue.text</span>
        <p className="text-amber whitespace-pre-wrap">{cue.text || <em className="text-txt-faint">(hold cue, no VO)</em>}</p>
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
