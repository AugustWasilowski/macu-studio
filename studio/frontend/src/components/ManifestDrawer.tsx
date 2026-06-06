import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "../api";
import { useStore } from "../store";
import { Field } from "./Field";
import { Dot } from "./Badge";
import { Collapsible as Section } from "./Collapsible";
import { IBrace, IPlus, IRegen, IX } from "./Icons";

export function ManifestDrawer({ slug, onJumpToStage }: { slug: string; onJumpToStage: (s: string) => void }) {
  const open = useStore((s) => s.drawerOpen);
  const close = useStore((s) => s.closeDrawer);
  const push = useStore((s) => s.pushToast);
  const qc = useQueryClient();

  const manifestQ = useQuery({
    queryKey: ["manifest", slug],
    queryFn: () => api.manifest(slug),
    enabled: !!slug && open,
  });

  const [m, setM] = useState<Record<string, any> | null>(null);
  const [raw, setRaw] = useState(false);
  const [rawText, setRawText] = useState("");
  const [rawErr, setRawErr] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (manifestQ.data) {
      setM(manifestQ.data);
      setRawText(JSON.stringify(manifestQ.data, null, 2));
      setDirty(false);
      setRawErr(null);
    }
  }, [manifestQ.data]);

  // Deep-clone-and-set
  function set(path: (string | number)[], v: unknown) {
    if (!m) return;
    const next = JSON.parse(JSON.stringify(m));
    let o: any = next;
    for (let i = 0; i < path.length - 1; i++) {
      if (o[path[i]] == null) o[path[i]] = typeof path[i + 1] === "number" ? [] : {};
      o = o[path[i]];
    }
    o[path[path.length - 1]] = v;
    setM(next);
    setRawText(JSON.stringify(next, null, 2));
    setDirty(true);
  }

  const save = useMutation({
    mutationFn: () => {
      const payload = raw
        ? (() => { try { setRawErr(null); return JSON.parse(rawText); } catch (e: any) { setRawErr(e.message); throw e; } })()
        : m!;
      return api.putManifest(slug, payload);
    },
    onSuccess: () => {
      setDirty(false);
      push("manifest.json written", "ok");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["cues", slug] });
      qc.invalidateQueries({ queryKey: ["shots", slug] });
      qc.invalidateQueries({ queryKey: ["titles", slug] });
    },
    onError: (e: Error) => push("save failed: " + e.message, "err"),
  });

  const speakerMap = useMemo(() => {
    if (!m?.voice?.speaker_map) return [] as { speaker: string; cfg: any }[];
    return Object.entries(m.voice.speaker_map as Record<string, any>)
      .map(([speaker, cfg]) => ({ speaker, cfg }));
  }, [m]);

  const characters = useMemo(() => {
    if (!m?.characters) return [] as { key: string; cfg: any }[];
    return Object.entries(m.characters as Record<string, any>)
      .map(([key, cfg]) => ({ key, cfg }));
  }, [m]);

  return (
    <>
      <div
        className={"fixed inset-0 z-[800] bg-black/40 transition-opacity " + (open ? "opacity-100" : "opacity-0 pointer-events-none")}
        onClick={close}
      />
      <aside
        className={"fixed top-0 right-0 h-full z-[900] panel flex flex-col transition-transform " + (open ? "translate-x-0" : "translate-x-full")}
        style={{ width: 520 }}
      >
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title flex items-center gap-2">
            <IBrace /> MANIFEST
            <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {slug}/manifest.json {dirty && <span className="text-amber">· UNSAVED</span>}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              className={"btn " + (raw ? "btn-amber" : "")}
              onClick={() => setRaw((v) => !v)}
            >{raw ? "Form view" : "View raw JSON"}</button>
            <button className="btn p-1" onClick={close}><IX /></button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
          {manifestQ.isLoading && <div className="text-txt-faint">Loading manifest…</div>}
          {manifestQ.error && <div className="text-red">Failed to load: {(manifestQ.error as Error).message}</div>}
          {m && !raw && (
            <>
              <Section title="Episode metadata">
                <Field label="title" value={m.title ?? ""} onChange={(v) => set(["title"], v)} />
                <div className="grid grid-cols-2 gap-2">
                  <Field label="episode" value={m.episode ?? ""} onChange={(v) => set(["episode"], v)} />
                  <Field label="version" value={m.version ?? ""} onChange={(v) => set(["version"], v)} />
                  <Field label="authored_by" value={m.authored_by ?? ""} onChange={(v) => set(["authored_by"], v)} />
                </div>
                {m.notes !== undefined && (
                  <Field label="notes" value={m.notes ?? ""} onChange={(v) => set(["notes"], v)} rows={3} />
                )}
              </Section>

              <Section title="Voice">
                {m.voice?.default && (
                  <div className="grid grid-cols-2 gap-2">
                    <Field
                      label="default.engine"
                      value={m.voice.default?.engine ?? ""}
                      onChange={(v) => set(["voice", "default", "engine"], v)}
                      options={["piper", "omnivoice", "xtts", "elevenlabs"]}
                    />
                    <Field
                      label="default.endpoint"
                      value={m.voice.default?.endpoint ?? ""}
                      onChange={(v) => set(["voice", "default", "endpoint"], v)}
                    />
                  </div>
                )}
                <div className="label-tiny mt-2">speaker_map</div>
                <div className="hairline-soft rounded">
                  <div className="grid grid-cols-[110px_90px_90px_1fr_80px_60px] gap-1 px-2 py-1 label-tiny border-b hairline-soft">
                    <span>SPEAKER</span><span>ENGINE</span><span>SPEED</span><span>VOICE</span><span>PROFILE</span><span></span>
                  </div>
                  {speakerMap.map(({ speaker, cfg }) => (
                    <div key={speaker} className="grid grid-cols-[110px_90px_90px_1fr_80px_60px] gap-1 px-2 py-1 items-center border-b border-[var(--line-soft)]">
                      <span className="font-bold text-amber">{speaker}</span>
                      <select
                        className="input"
                        value={cfg.engine ?? "piper"}
                        onChange={(e) => set(["voice", "speaker_map", speaker, "engine"], e.target.value)}
                      >
                        <option value="piper">piper</option>
                        <option value="omnivoice">omnivoice</option>
                        <option value="xtts">xtts</option>
                        <option value="elevenlabs">elevenlabs</option>
                      </select>
                      <input
                        className="input"
                        type="number"
                        step="0.05"
                        value={cfg.speed ?? 1.0}
                        onChange={(e) => set(["voice", "speaker_map", speaker, "speed"], parseFloat(e.target.value))}
                      />
                      <input
                        className="input"
                        value={cfg.voice_name ?? ""}
                        onChange={(e) => set(["voice", "speaker_map", speaker, "voice_name"], e.target.value)}
                      />
                      <input
                        className="input"
                        value={cfg.profile_id ?? ""}
                        onChange={(e) => set(["voice", "speaker_map", speaker, "profile_id"], e.target.value)}
                      />
                      <button
                        className="btn p-1"
                        title="Regenerate sample (defers to Stage 2)"
                        onClick={() => { onJumpToStage("audio"); close(); }}
                      ><IRegen /></button>
                    </div>
                  ))}
                </div>
              </Section>

              {m.comfyui && (
                <Section title="ComfyUI">
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="checkpoint" value={m.comfyui.checkpoint ?? ""} onChange={(v) => set(["comfyui", "checkpoint"], v)} dot="rendered" />
                    <Field label="workflow" value={m.comfyui.workflow ?? ""} onChange={(v) => set(["comfyui", "workflow"], v)} />
                    <Field label="width" value={m.comfyui.width ?? 0} type="number" onChange={(v) => set(["comfyui", "width"], +v)} />
                    <Field label="height" value={m.comfyui.height ?? 0} type="number" onChange={(v) => set(["comfyui", "height"], +v)} />
                    <Field label="frames" value={m.comfyui.frames ?? 0} type="number" onChange={(v) => set(["comfyui", "frames"], +v)} />
                    <Field label="steps" value={m.comfyui.steps ?? 0} type="number" onChange={(v) => set(["comfyui", "steps"], +v)} />
                    <Field label="cfg" value={m.comfyui.cfg ?? 0} type="number" onChange={(v) => set(["comfyui", "cfg"], +v)} />
                  </div>
                </Section>
              )}

              {m.style && (
                <Section title="Style">
                  <Field label="suffix" value={m.style.suffix ?? ""} onChange={(v) => set(["style", "suffix"], v)} rows={3} />
                  <Field label="negative" value={m.style.negative ?? ""} onChange={(v) => set(["style", "negative"], v)} rows={3} />
                </Section>
              )}

              {characters.length > 0 && (
                <Section title={`Characters (${characters.length})`}>
                  {characters.map(({ key, cfg }) => (
                    <div key={key} className="hairline-soft rounded p-2 mb-1.5">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-amber">{key}</span>
                        <Field
                          label=""
                          value={cfg.seed ?? 0}
                          type="number"
                          onChange={(v) => set(["characters", key, "seed"], parseInt(v, 10) || 0)}
                        />
                      </div>
                      <Field
                        label="core prompt"
                        value={cfg.core ?? ""}
                        onChange={(v) => set(["characters", key, "core"], v)}
                        rows={2}
                      />
                    </div>
                  ))}
                </Section>
              )}

              {m.music && (
                <Section title="Music">
                  <ToggleRow
                    label="enabled"
                    on={!!m.music.enabled}
                    onChange={(v) => set(["music", "enabled"], v)}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="gain" value={m.music.gain ?? 0} type="number" onChange={(v) => set(["music", "gain"], parseFloat(v) || 0)} />
                    <Field label="clip_seconds" value={m.music.clip_seconds ?? 0} type="number" onChange={(v) => set(["music", "clip_seconds"], parseFloat(v) || 0)} />
                    <Field label="fade_in" value={m.music.fade_in ?? 0} type="number" onChange={(v) => set(["music", "fade_in"], parseFloat(v) || 0)} />
                    <Field label="fade_out" value={m.music.fade_out ?? 0} type="number" onChange={(v) => set(["music", "fade_out"], parseFloat(v) || 0)} />
                  </div>
                  <div className="label-tiny mt-1">clips</div>
                  {(m.music.clips ?? []).map((c: string, i: number) => (
                    <div key={i} className="flex items-center gap-2 py-1">
                      <Dot status="ok" />
                      <input
                        className="input flex-1 font-mono"
                        value={c}
                        onChange={(e) => {
                          const arr = [...m.music.clips];
                          arr[i] = e.target.value;
                          set(["music", "clips"], arr);
                        }}
                      />
                      <button
                        className="btn p-1"
                        onClick={() => set(["music", "clips"], m.music.clips.filter((_: any, j: number) => j !== i))}
                      ><IX /></button>
                    </div>
                  ))}
                  <button className="btn" onClick={() => set(["music", "clips"], [...(m.music.clips ?? []), "new_clip.mp3"])}>
                    <IPlus /> Add clip
                  </button>
                </Section>
              )}

              {m.subtitles && (
                <Section title="Subtitles">
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="font" value={m.subtitles.font ?? ""} onChange={(v) => set(["subtitles", "font"], v)} dot="rendered" />
                    <Field label="fontsize" value={m.subtitles.fontsize ?? 0} type="number" onChange={(v) => set(["subtitles", "fontsize"], parseInt(v, 10) || 0)} />
                    <Field label="fontsdir" value={m.subtitles.fontsdir ?? ""} onChange={(v) => set(["subtitles", "fontsdir"], v)} />
                    <Field label="font_file" value={m.subtitles.font_file ?? ""} onChange={(v) => set(["subtitles", "font_file"], v)} />
                  </div>
                  <Field label="force_style" value={m.subtitles.force_style ?? ""} onChange={(v) => set(["subtitles", "force_style"], v)} rows={2} />
                </Section>
              )}

              <Section title="SFX">
                <div
                  className="hairline-soft rounded p-3 flex items-center justify-between cursor-pointer hover:bg-bg-3"
                  onClick={() => { onJumpToStage("audio"); close(); }}
                >
                  <span>{(m.sfx ?? []).length} SFX entries pinned to cues</span>
                  <span className="text-cyan">Manage in Stage 2 — Audio →</span>
                </div>
              </Section>
            </>
          )}
          {m && raw && (
            <>
              <textarea
                className="input font-mono"
                style={{ height: "calc(100vh - 220px)", whiteSpace: "pre", resize: "none" }}
                value={rawText}
                onChange={(e) => { setRawText(e.target.value); setDirty(true); }}
              />
              {rawErr && <div className="text-red text-[11px] mt-1">JSON error: {rawErr}</div>}
            </>
          )}
        </div>
        <footer className="flex items-center justify-between px-3 py-2 border-t hairline">
          <span className="label-tiny">{dirty ? "modified · unsaved" : "in sync with disk"}</span>
          <button
            className="btn btn-amber"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Save manifest"}
          </button>
        </footer>
      </aside>
    </>
  );
}

function ToggleRow({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between">
      <span className="label-tiny">{label}</span>
      <button
        onClick={() => onChange(!on)}
        className="w-10 h-5 rounded-full relative border"
        style={{
          background: on ? "rgba(245,166,35,0.20)" : "rgba(255,255,255,0.05)",
          borderColor: on ? "var(--amber)" : "var(--line-soft)",
        }}
      >
        <span
          className="absolute top-0.5 transition-all"
          style={{
            left: on ? 22 : 2,
            width: 14,
            height: 14,
            borderRadius: 999,
            background: on ? "var(--amber)" : "var(--txt-dim)",
            boxShadow: on ? "var(--glow-amber)" : undefined,
          }}
        />
      </button>
    </label>
  );
}
