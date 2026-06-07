import { Fragment, useMemo, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "../api";
import { voicesApi } from "../api/voices";
import { useStore } from "../store";

/** Deterministic color per character (same palette as the cue rows). */
function colorFor(name: string): string {
  if (!name) return "#938d82";
  const palette = ["#f5a623", "#00e5ff", "#33ff66", "#c08bff", "#ff7a59", "#9ad6ff", "#ffd166", "#7cc97a"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return palette[Math.abs(h) % palette.length];
}

/** Cast → voice assignment for the Audio page. Lists every character "so far in
 * the show" — the recurring cast carried in the manifest, anyone already voiced,
 * script speakers, plus anything added via "+ Add character" (e.g. NARRATOR) —
 * and lets you pick a cloned OmniVoice voice for each. Keys/dedupes by UPPERCASE
 * label (the script speaker label the renderer matches). Writes the current
 * episode's manifest.voice.speaker_map; "Select a voice…" clears it. The voice
 * list is cached server-side, so the roster (incl. the Announcer) shows even
 * when OmniVoice is stopped. */
export function VoicePicker({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const manifestQ = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });
  const cuesQ = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug) });
  const voicesQ = useQuery({ queryKey: ["voices"], queryFn: voicesApi.list });

  const [added, setAdded] = useState<string[]>([]);
  const [newName, setNewName] = useState("");

  const m = manifestQ.data as any;
  const speakerMap = (m?.voice?.speaker_map ?? {}) as Record<string, any>;

  const characters = useMemo(() => {
    const set = new Set<string>();
    const add = (raw?: string) => { const u = (raw || "").trim().toUpperCase(); if (u) set.add(u); };
    Object.keys(m?.characters ?? {}).forEach(add);  // recurring cast (seeded from show defaults)
    Object.keys(speakerMap).forEach(add);            // anyone already voiced
    (cuesQ.data?.cues ?? []).forEach((c: any) => add(c.speaker)); // script speakers (once cues exist)
    added.forEach(add);                              // locally added (e.g. NARRATOR)
    return [...set];
  }, [m, cuesQ.data, added]);

  const running = voicesQ.data?.running ?? false;
  const cached = voicesQ.data?.cached ?? false;

  const voiceOptions = useMemo(() => {
    const byId = new Map<string, string>();
    for (const p of voicesQ.data?.profiles ?? []) byId.set(p.id, p.name);
    for (const k of Object.keys(speakerMap)) {
      const e = speakerMap[k];
      if (e?.profile_id && !byId.has(e.profile_id)) byId.set(e.profile_id, e.voice_name || e.profile_id);
    }
    return [...byId.entries()].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [voicesQ.data, speakerMap]);

  const mut = useMutation({
    mutationFn: ({ speaker, profile_id }: { speaker: string; profile_id: string }) =>
      profile_id
        ? api.setSpeakerVoice(slug, speaker, "omnivoice", profile_id, voiceOptions.find((o) => o.id === profile_id)?.name)
        : api.setSpeakerVoice(slug, speaker, "piper"),
    onSuccess: (r, v) => {
      const label = v.profile_id ? (voiceOptions.find((o) => o.id === v.profile_id)?.name ?? "voice") : "unassigned";
      push(`${v.speaker} → ${label}${r.propagated ? " · saved for all episodes" : ""}`, "ok");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["cues", slug] });
    },
    onError: (e: Error) => push("voice update failed: " + e.message, "err"),
  });

  const addChar = () => {
    const u = newName.trim().toUpperCase();
    if (u) { setAdded((a) => (a.includes(u) ? a : [...a, u])); setNewName(""); }
  };

  const voiceCountNote = running
    ? `${voiceOptions.length} voice${voiceOptions.length === 1 ? "" : "s"}`
    : cached && voiceOptions.length
      ? `${voiceOptions.length} voices (OmniVoice stopped — cached)`
      : "OmniVoice stopped — clone or render to list voices";

  return (
    <div className="px-3 py-2 border-b hairline flex flex-col gap-2 bg-bg-1">
      <div className="flex items-center justify-between">
        <span className="label-tiny">CAST VOICES <span className="text-txt-faint normal-case tracking-normal">— assign a cloned voice per character</span></span>
        <span className="label-tiny text-txt-faint">{voiceCountNote}</span>
      </div>

      {characters.length === 0 && (
        <div className="label-tiny text-txt-faint">No characters yet — add one below, or Generate manifest to pull them from the script.</div>
      )}

      <div className="grid grid-cols-[minmax(110px,180px)_1fr] gap-x-3 gap-y-1.5 items-center">
        {characters.map((spk) => {
          const cur = speakerMap[spk]?.engine === "omnivoice" ? (speakerMap[spk]?.profile_id || "") : "";
          return (
            <Fragment key={spk}>
              <span className="flex items-center gap-1.5 text-[12px] min-w-0">
                <span className="led-dot shrink-0" style={{ "--led-c": colorFor(spk) } as React.CSSProperties} />
                <span className="font-mono truncate">{spk}</span>
              </span>
              <select
                className="input py-0.5 text-[12px]"
                value={cur}
                onChange={(e) => mut.mutate({ speaker: spk, profile_id: e.target.value })}
                disabled={mut.isPending}
              >
                <option value="">Select a voice…</option>
                {voiceOptions.map((o) => (<option key={o.id} value={o.id}>{o.name}</option>))}
              </select>
            </Fragment>
          );
        })}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <input
          className="input py-0.5 text-[12px] w-[200px]"
          placeholder="+ Add character (e.g. NARRATOR)"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") addChar(); }}
        />
        <button className="btn" onClick={addChar} disabled={!newName.trim()}>Add</button>
      </div>
    </div>
  );
}
