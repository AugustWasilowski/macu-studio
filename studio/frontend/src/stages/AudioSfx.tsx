import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { libraryApi, AssetKind, SfxEntry } from "../api/library";
import { useStore } from "../store";
import { Modal } from "../components/Modal";
import { Field } from "../components/Field";
import { PlayBtn } from "../components/PlayBtn";
import { IPlus, IX } from "../components/Icons";
import { resolveMedia } from "../mediaCache";

// One item in the continuous-playback queue (VO cue or an SFX one-shot).
export interface PlayItem { url: string; cueId?: string; label: string; }

const round2 = (n: number) => Math.round(n * 100) / 100;

// Module-level drag payload (more reliable than dataTransfer across dragover/drop).
let drag: { type: "lib" | "sfx"; file?: string; idx?: number } | null = null;

// ---- single-clip preview player (audition a library / gap SFX) ----
export function usePreview() {
  const [previewUrl, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!previewUrl) return;
    const a = new window.Audio(resolveMedia(previewUrl));
    a.onended = () => setUrl(null);
    a.onerror = () => setUrl(null);
    a.play().catch(() => setUrl(null));
    return () => { a.pause(); };
  }, [previewUrl]);
  return { previewUrl, toggle: (url: string) => setUrl((p) => (p === url ? null : url)) };
}

// ---- SFX placement logic (shared by the interleaved cue table) ----
// SFX live in the GAP after a cue (cN at:end) or before the next (cN+1 at:start).
export function useSfx(slug: string) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });
  const cuesQ = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug) });
  const sfxLib = useQuery({ queryKey: ["assets", "sfx"], queryFn: () => libraryApi.list("sfx") });

  const m = manifest.data as any;
  const sfx: SfxEntry[] = Array.isArray(m?.sfx) ? m.sfx : [];
  const cueRows = cuesQ.data?.cues ?? [];
  const cueIds = cueRows.map((c) => c.id);

  const durOf = useMemo(() => {
    const map: Record<string, number> = {};
    (sfxLib.data ?? []).forEach((a) => { if (a.duration_s != null) map[a.file] = a.duration_s; });
    return map;
  }, [sfxLib.data]);

  const idxOf = (cid: string | null) => (cid == null ? -1 : cueIds.indexOf(cid));
  const afterCueOf = (e: SfxEntry): string | null => {
    if (e.at === "start") { const i = idxOf(e.cue); return i > 0 ? cueIds[i - 1] : null; }
    return e.cue ?? null;
  };

  const normalize = (entries: SfxEntry[]): SfxEntry[] => {
    const buckets = new Map<string, SfxEntry[]>();
    for (const e of entries) {
      const key = afterCueOf(e) ?? " ";
      (buckets.get(key) ?? buckets.set(key, []).get(key)!).push(e);
    }
    const order = [" ", ...cueIds];
    const out: SfxEntry[] = [];
    for (const key of order) {
      const grp = buckets.get(key);
      if (!grp) continue;
      // Auto-stagger only SEEDS a delay for entries that don't have one yet
      // (freshly dropped). Entries with an explicit delay (incl. user-edited)
      // are preserved — manual delay nudges survive subsequent commits.
      let cum = 0;
      for (const e of grp) {
        const delay = e.delay == null ? round2(cum) : e.delay;
        out.push({ ...e, delay });
        cum += durOf[e.file] ?? 0.5;
      }
      buckets.delete(key);
    }
    for (const grp of buckets.values()) out.push(...grp);
    return out;
  };

  const putSfx = useMutation({
    mutationFn: (next: SfxEntry[]) => libraryApi.putSfx(slug, next),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }),
    onError: (e: Error) => push("sfx save failed: " + e.message, "err"),
  });
  const commit = (next: SfxEntry[]) => putSfx.mutate(normalize(next));

  const addToGap = (afterId: string | null, file: string) => {
    const cue = afterId ?? cueIds[0] ?? null;
    if (!cue) { push("no cues to pin to", "err"); return; }
    commit([...sfx, { file, cue, at: afterId ? "end" : "start", gain: 0.4, fade: 0, source: "library" }]);
    push(`${file} → ${afterId ? `after ${afterId}` : `before ${cue}`}`, "ok");
  };
  const moveEntry = (idx: number, afterId: string | null) => {
    const e = sfx[idx]; if (!e) return;
    const cue = afterId ?? cueIds[0] ?? null; if (!cue) return;
    const next = sfx.filter((_, i) => i !== idx);
    next.push({ ...e, cue, at: afterId ? "end" : "start" });
    commit(next);
  };
  const del = (idx: number) => commit(sfx.filter((_, i) => i !== idx));
  const setGain = (idx: number, g: number) => { const next = [...sfx]; next[idx] = { ...next[idx], gain: g }; commit(next); };
  const setDelay = (idx: number, d: number) => { const next = [...sfx]; next[idx] = { ...next[idx], delay: d }; commit(next); };
  const onDropGap = (afterId: string | null) => {
    if (!drag) return;
    if (drag.type === "lib" && drag.file) addToGap(afterId, drag.file);
    else if (drag.type === "sfx" && drag.idx != null) moveEntry(drag.idx, afterId);
    drag = null;
  };
  const entriesByGap = (afterId: string | null) =>
    sfx.map((x, i) => ({ x, i })).filter((o) => afterCueOf(o.x) === afterId);

  // Interleaved VO + SFX playlist for continuous playback.
  const buildPlaylist = (): PlayItem[] => {
    const items: PlayItem[] = [];
    const gapItems = (afterId: string | null) =>
      [...entriesByGap(afterId)]
        .sort((a, b) => (a.x.delay ?? 0) - (b.x.delay ?? 0))
        .map(({ x }) => ({ url: libraryApi.audioUrl("sfx", x.file), label: `sfx ${x.file}` }));
    items.push(...gapItems(null));
    for (const c of cueRows) {
      if (c.wav_exists) items.push({ url: mediaUrl.cueAudio(slug, c.id, c.wav_mtime), cueId: c.id, label: c.id });
      items.push(...gapItems(c.id));
    }
    return items;
  };

  // Every distinct audio URL for this episode (versioned cue wavs + SFX clips),
  // for the "Pre-cache audio" button. URLs match what buildPlaylist/playback use
  // so the blob cache keys line up.
  const precacheUrls = (): string[] => {
    const urls: string[] = [];
    const seen = new Set<string>();
    const add = (u: string) => { if (!seen.has(u)) { seen.add(u); urls.push(u); } };
    for (const c of cueRows) {
      if (c.wav_exists) add(mediaUrl.cueAudio(slug, c.id, c.wav_mtime));
    }
    for (const e of sfx) add(libraryApi.audioUrl("sfx", e.file));
    return urls;
  };

  return {
    sfx, cueIds, durOf,
    gapsOrder: [null, ...cueIds] as (string | null)[],
    entriesByGap, addToGap, moveEntry, del, setGain, setDelay, onDropGap, buildPlaylist, precacheUrls,
  };
}

// ---- one gap (dropzone + its SFX rows), rendered inside a table <td> ----
export function GapZone({ entries, onDrop, onDelete, onGain, onDelay, onPlay, previewUrl }: {
  entries: { x: SfxEntry; i: number }[];
  onDrop: () => void;
  onDelete: (idx: number) => void;
  onGain: (idx: number, g: number) => void;
  onDelay: (idx: number, d: number) => void;
  onPlay: (file: string) => void;
  previewUrl: string | null;
}) {
  const [over, setOver] = useState(false);
  const empty = entries.length === 0;
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={() => { setOver(false); onDrop(); }}
      className={"pl-9 pr-1 " + (over ? "bg-bg-3 outline outline-1 outline-[var(--cyan)]" : "")}
    >
      {empty ? (
        <div className="text-txt-faint text-[10px] italic" style={{ height: over ? 14 : 5, lineHeight: "12px" }}>
          {over ? "drop SFX here" : ""}
        </div>
      ) : (
        entries.map(({ x, i }) => {
          const url = libraryApi.audioUrl("sfx", x.file);
          return (
            <div key={i} draggable onDragStart={() => { drag = { type: "sfx", idx: i }; }}
              className="flex items-center gap-2 py-0.5 hover:bg-bg-3 rounded cursor-grab text-[11px]">
              <span className="text-cyan">▸</span>
              <PlayBtn playing={previewUrl === url} onClick={() => onPlay(x.file)} />
              <span className="font-mono text-cyan flex-1 truncate" title={x.file}>{x.file}</span>
              <label className="flex items-center gap-1 text-txt-faint text-[10px]" title="delay nudge — seconds, signed (− earlier / + later from the anchor cue)">
                Δs
                <input className="input w-16 text-[11px] py-0" type="number" step="0.1" value={x.delay ?? 0}
                  onChange={(e) => { const v = parseFloat(e.target.value); onDelay(i, Number.isFinite(v) ? round2(v) : 0); }} />
              </label>
              <label className="flex items-center gap-1 text-txt-faint text-[10px]" title="gain — 0–1 linear">
                g
                <input className="input w-20 text-[11px] py-0" type="number" step="0.05" value={x.gain ?? 0.4}
                  onChange={(e) => onGain(i, parseFloat(e.target.value))} />
              </label>
              <button className="btn p-0.5" title="remove" onClick={() => onDelete(i)}><IX /></button>
            </div>
          );
        })
      )}
    </div>
  );
}

// ---- library (browse + drag) + the generate/fetch dialog; lives under the inspector ----
export function Library({ slug, previewUrl, onPreview }: {
  slug: string; previewUrl: string | null; onPreview: (url: string) => void;
}) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [tab, setTab] = useState<AssetKind>("sfx");
  const [filter, setFilter] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const q = useQuery({ queryKey: ["assets", tab], queryFn: () => libraryApi.list(tab) });
  const cuesQ = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug) });
  const cueIds = cuesQ.data?.cues.map((c) => c.id) ?? [];
  const addBed = useMutation({
    mutationFn: (file: string) => libraryApi.addBed(slug, file),
    onSuccess: (r, file) => {
      push(r.added ? `${file} → music beds` : `${file} already a bed`, r.added ? "ok" : "info");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
    },
    onError: (e: Error) => push("add bed failed: " + e.message, "err"),
  });
  const items = q.data ?? [];
  const fq = filter.trim().toLowerCase();
  const shown = fq
    ? items.filter((a) =>
        a.file.toLowerCase().includes(fq) ||
        (a.notes ?? "").toLowerCase().includes(fq) ||
        (a.source ?? "").toLowerCase().includes(fq))
    : items;

  return (
    <section className="panel flex flex-col min-h-0 flex-1">
      <header className="flex items-center justify-between px-3 py-2 border-b hairline">
        <div className="panel-title">LIBRARY <span className="text-txt-faint">/ drag SFX → a cue gap</span></div>
        <button className="btn btn-cyan" onClick={() => setAddOpen(true)}><IPlus /> Add</button>
      </header>
      <div className="flex gap-1 px-2 pt-2">
        {(["sfx", "music"] as const).map((k) => (
          <button key={k} onClick={() => setTab(k)}
            className={"tab px-2 h-[24px] hairline-soft rounded-[3px] text-[10px] uppercase tracking-wider " + (tab === k ? "active" : "")}
            style={tab === k ? { borderColor: "var(--cyan)", boxShadow: "var(--glow-cyan)", color: "var(--cyan)" } : {}}>
            {k} <span className="text-txt-faint">{tab === k ? (fq ? `${shown.length}/${items.length}` : items.length) : ""}</span>
          </button>
        ))}
      </div>
      <input
        className="input mx-2 mt-2 text-[11px]"
        placeholder={`filter ${tab}… (name / notes)`}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="overflow-y-auto flex-1 p-2 text-[12px]">
        {shown.length === 0 ? (
          <div className="text-txt-faint text-[11px] p-1">
            {q.isLoading ? "loading…" : items.length === 0 ? "empty" : "no match"}
          </div>
        ) : (
          shown.map((a) => {
            const url = libraryApi.audioUrl(tab, a.file);
            return (
              <div key={a.file} draggable={tab === "sfx"}
                onDragStart={() => { if (tab === "sfx") drag = { type: "lib", file: a.file }; }}
                className={"flex items-center gap-1.5 py-0.5 hover:bg-bg-3 rounded " + (tab === "sfx" ? "cursor-grab" : "")}
                title={a.notes || a.source || ""}>
                <PlayBtn playing={previewUrl === url} onClick={() => onPreview(url)} />
                <span className="font-mono flex-1 truncate" title={a.file}>{a.file}</span>
                <span className="text-txt-faint text-[10px]">{a.duration_s != null ? `${a.duration_s}s` : ""}</span>
                {tab === "music"
                  ? <button className="btn p-0.5 px-1 text-[10px]" onClick={() => addBed.mutate(a.file)}>+ bed</button>
                  : <span className="text-txt-faint text-[10px]" title="drag into a cue gap">⠿</span>}
              </div>
            );
          })
        )}
      </div>
      <AddSfxDialog open={addOpen} onClose={() => setAddOpen(false)} slug={slug} cueIds={cueIds}
        initialSource={tab === "music" ? "music" : "freesound"}
        onAdded={() => {
          qc.invalidateQueries({ queryKey: ["manifest", slug] });
          qc.invalidateQueries({ queryKey: ["assets", "sfx"] });
          qc.invalidateQueries({ queryKey: ["assets", "music"] });
        }} />
    </section>
  );
}

type AddSource = "freesound" | "generate" | "music";

export function AddSfxDialog({ open, onClose, slug, cueIds, onAdded, initialSource = "freesound" }: {
  open: boolean;
  onClose: () => void;
  slug: string;
  cueIds: string[];
  onAdded: () => void;
  initialSource?: AddSource;
}) {
  const push = useStore((s) => s.pushToast);
  const [source, setSource] = useState<AddSource>(initialSource);
  const [query, setQuery] = useState("");
  const [duration, setDuration] = useState("4");
  const [seed, setSeed] = useState("");
  const [engine, setEngine] = useState<"music" | "riff">("music"); // music-gen model
  const [cue, setCue] = useState(cueIds[0] ?? "");
  const [at, setAt] = useState("start");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => { if (cueIds.length && !cue) setCue(cueIds[0]); }, [cueIds, cue]);
  // Reset on open; default the source/duration to the tab that opened it.
  useEffect(() => {
    if (open) {
      setSource(initialSource);
      setQuery(""); setSeed(""); setResult(null); setBusy(false);
      setDuration(initialSource === "music" ? "20" : "4");
    }
  }, [open, initialSource]);

  const isMusic = source === "music";
  const isGen = source === "generate";

  const pickSource = (s: AddSource) => {
    setSource(s); setResult(null);
    if (s === "music" && (duration === "4" || !duration)) setDuration("20");
    if (s !== "music" && duration === "20") setDuration("4");
  };

  const submit = async () => {
    if (!query.trim()) return;
    setBusy(true); setResult(null);
    const verb = isMusic ? "music gen" : isGen ? "generate" : "fetch";
    try {
      let url: string, body: any;
      if (isMusic) {
        url = `/api/episodes/${slug}/music/gen`;
        body = { prompt: query, engine, duration: parseFloat(duration) || 20, seed: seed ? parseInt(seed, 10) : null };
      } else if (isGen) {
        url = `/api/episodes/${slug}/sfx/gen`;
        body = { prompt: query, duration: parseFloat(duration) || 3, seed: seed ? parseInt(seed, 10) : null, cue_id: cue || null, at };
      } else {
        url = `/api/episodes/${slug}/sfx/fetch`;
        body = { query, duration_max: parseFloat(duration) || 4, cue_id: cue || null, at };
      }
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await r.json();
      setResult(data);
      if (r.status === 409) {
        push("GPU busy — a render is active. Try again when idle.", "err");
      } else if (data.ok) {
        push(isMusic ? "music bed generated" : isGen ? "SFX generated and pinned" : "SFX fetched and pinned", "ok");
        onAdded();
      } else {
        push(`${verb}: ${data.hint ?? data.detail ?? "no match"}`, "info");
      }
    } catch (e: any) {
      push(`${verb} failed: ` + e.message, "err");
    }
    setBusy(false);
  };

  return (
    <Modal open={open} onClose={onClose} title="GENERATE / FETCH AUDIO" width={520}
      footer={
        <>
          <button className="btn" onClick={onClose}>Close</button>
          <button className="btn btn-cyan" disabled={busy || !query.trim()} onClick={submit}>
            {busy
              ? (isMusic || isGen ? "Generating…" : "Fetching…")
              : (isMusic ? "Generate music" : isGen ? "Generate (agen)" : "Search Freesound")}
          </button>
        </>
      }>
      <div className="flex flex-col gap-2">
        <div className="flex gap-1">
          {([["freesound", "Freesound SFX"], ["generate", "Generate SFX"], ["music", "Generate Music"]] as const).map(([s, label]) => (
            <button key={s} onClick={() => pickSource(s)}
              className={"tab px-3 h-[28px] hairline-soft rounded-[3px] text-[11px] uppercase tracking-wider " + (source === s ? "active" : "")}
              style={source === s ? { borderColor: "var(--cyan)", boxShadow: "var(--glow-cyan)", color: "var(--cyan)" } : {}}>
              {label}
            </button>
          ))}
        </div>
        <Field
          label={isMusic ? "music prompt (MusicGen/Riffusion)" : isGen ? "agen prompt (AudioGen foley)" : "freesound query"}
          value={query} onChange={setQuery}
          placeholder={isMusic ? "e.g. ‘sickly lo-fi big-band waltz, tape hiss, mono’"
            : isGen ? "e.g. ‘heavy iron door slam, dry, close mic’"
            : "e.g. ‘old radio transmitter hum’"} />
        <div className="grid grid-cols-2 gap-2">
          <Field label={isMusic || isGen ? "duration" : "duration max"} value={duration} onChange={setDuration} type="number" suffix="s" />
          {isMusic
            ? <Field label="model" value={engine} onChange={(v) => setEngine(v as "music" | "riff")} options={["music", "riff"]} />
            : isGen
              ? <Field label="seed (optional)" value={seed} onChange={setSeed} type="number" placeholder="auto" />
              : <Field label="at" value={at} onChange={setAt} options={["start", "end"]} />}
          {isMusic && <Field label="seed (optional)" value={seed} onChange={setSeed} type="number" placeholder="auto" />}
          {isGen && <Field label="at" value={at} onChange={setAt} options={["start", "end"]} />}
          {!isMusic && <Field label="cue pin" value={cue} onChange={setCue} options={cueIds.length ? cueIds : [""]} />}
        </div>
        <div className="text-[11px] text-txt-faint">
          {isMusic
            ? <>Local {engine === "riff" ? "Riffusion (grittier lo-fi)" : "MusicGen"} → a bed added to <span className="text-cyan">music.clips[]</span> · won't run during a render</>
            : isGen
              ? <>Local AudioGen → 24 kHz/−3 dBFS into the kit · pinned to <span className="text-cyan">{at} of @{cue || "—"}</span> · then drag it from the library</>
              : <>CC0 clips only · pinned to <span className="text-cyan">{at} of @{cue || "—"}</span> · then drag it from the library</>}
        </div>
        {result && (
          <pre className="logtail" style={{ height: 140 }}>{result.ok
            ? `OK\n${result.log ?? ""}`
            : `FAILED${result.returncode != null ? ` rc=${result.returncode}` : ""}\n${result.log ?? result.detail ?? ""}\n\nhint: ${result.hint ?? ""}`}</pre>
        )}
      </div>
    </Modal>
  );
}
