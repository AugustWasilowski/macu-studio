import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { Field } from "./Field";
import { useStore } from "../store";
import { showsApi } from "../api/shows";
import { THEMES, currentTheme, setTheme } from "../theme";

type Tab = "theme" | "show" | "git" | "comfy";

const TABS: { id: Tab; label: string }[] = [
  { id: "theme", label: "Appearance" },
  { id: "show", label: "Show metadata" },
  { id: "git", label: "Git repository" },
  { id: "comfy", label: "ComfyUI models" },
];

export function Settings({ show, onClose }: { show: string; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("theme");
  return (
    <Modal open onClose={onClose} title="Settings" width={680}>
      <div className="flex gap-3 min-h-[320px]">
        <div className="flex flex-col gap-1 w-[150px] shrink-0 border-r hairline-soft pr-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={"text-left px-2 py-1.5 rounded text-[12px] " + (tab === t.id ? "btn-amber" : "hover:bg-bg-3")}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-0">
          {tab === "theme" && <ThemePanel />}
          {tab === "show" && <ShowPanel show={show} onClose={onClose} />}
          {tab === "git" && <Stub title="Git repository"
            body="Configure the remote URL and branch the Studio syncs script/manifest/youtube to. Credentials use the box's existing SSH key. Coming soon." />}
          {tab === "comfy" && <Stub title="ComfyUI model manager"
            body="Browse checkpoints on the ComfyUI server (:8188) and pick a default per show. Coming soon." />}
        </div>
      </div>
    </Modal>
  );
}

function ThemePanel() {
  const [sel, setSel] = useState(currentTheme());
  return (
    <div className="flex flex-col gap-3">
      <div className="label-tiny">Color theme</div>
      <p className="label-tiny leading-relaxed">Recolors the primary accent. Applies instantly and is remembered on this device.</p>
      <div className="flex flex-col gap-2">
        {THEMES.map((t) => (
          <button
            key={t.id}
            className={"flex items-center gap-3 px-3 py-2 rounded hairline-soft text-left " + (sel === t.id ? "btn-amber" : "hover:bg-bg-3")}
            onClick={() => { setTheme(t.id); setSel(t.id); }}
          >
            <span className="rounded-full" style={{ width: 16, height: 16, background: t.accent, boxShadow: `0 0 7px ${t.accent}` }} />
            <span className="text-[12px]">{t.label}</span>
            {sel === t.id && <span className="label-tiny ml-auto">active</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function ShowPanel({ show, onClose }: { show: string; onClose: () => void }) {
  const qc = useQueryClient();
  const pushToast = useStore((s) => s.pushToast);
  const cfg = useQuery({ queryKey: ["show-config", show], queryFn: () => showsApi.config(show) });

  const [name, setName] = useState("");
  const [prefix, setPrefix] = useState("");
  const [assets, setAssets] = useState("");
  const [defaults, setDefaults] = useState<Record<string, any>>({});
  const [advanced, setAdvanced] = useState(false);
  const [advText, setAdvText] = useState("");
  const [advErr, setAdvErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!cfg.data) return;
    setName(cfg.data.name || "");
    setPrefix(cfg.data.title_prefix || "");
    setAssets(cfg.data.assets_dir || "");
    const d = (cfg.data.episode_defaults as Record<string, any>) || {};
    setDefaults(d);
    setAdvText(JSON.stringify(d, null, 2));
  }, [cfg.data]);

  // Nested-path setter for the convenience fields (keeps a single defaults source of truth).
  function setPath(path: string[], value: any) {
    setDefaults((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      let o = next;
      for (let i = 0; i < path.length - 1; i++) o = o[path[i]] ??= {};
      o[path[path.length - 1]] = value;
      setAdvText(JSON.stringify(next, null, 2));
      return next;
    });
  }
  const get = (path: string[]): string => {
    let o: any = defaults;
    for (const k of path) { if (o == null) return ""; o = o[k]; }
    return o == null ? "" : String(o);
  };

  function onAdv(text: string) {
    setAdvText(text);
    try { setDefaults(JSON.parse(text)); setAdvErr(""); }
    catch (e) { setAdvErr(e instanceof Error ? e.message : "invalid JSON"); }
  }

  async function save() {
    if (advErr) { pushToast("fix the episode_defaults JSON first", "err"); return; }
    setBusy(true);
    try {
      await showsApi.putConfig(show, { name, title_prefix: prefix, assets_dir: assets, episode_defaults: defaults });
      pushToast(`show '${show}' saved`, "ok");
      qc.invalidateQueries({ queryKey: ["show-config", show] });
      qc.invalidateQueries({ queryKey: ["shows"] });
    } catch (e) {
      pushToast(`save failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setBusy(false); }
  }

  if (cfg.isLoading) return <div className="text-txt-dim p-4">Loading…</div>;
  if (cfg.isError) return <div className="text-red p-4">Failed to load show config.</div>;

  return (
    <div className="flex flex-col gap-3 max-h-[440px] overflow-y-auto pr-1">
      <div className="label-tiny">{show}{cfg.data?.id === "the-macu-report" ? " (default)" : ""}</div>
      <Field label="Display name" value={name} onChange={setName} />
      <Field label="Episode title prefix" value={prefix} onChange={setPrefix} placeholder="My Show — " />
      <Field label="Assets dir (fonts/music/sfx)" value={assets} onChange={setAssets} monospace />
      <div className="label-tiny pt-1 border-t hairline-soft">Episode defaults (seed new episodes)</div>
      <Field label="Style suffix" value={get(["style", "suffix"])} onChange={(v) => setPath(["style", "suffix"], v)} rows={3} />
      <Field label="Style negative" value={get(["style", "negative"])} onChange={(v) => setPath(["style", "negative"], v)} rows={3} />
      <Field label="ComfyUI checkpoint" value={get(["comfyui", "checkpoint"])} onChange={(v) => setPath(["comfyui", "checkpoint"], v)} />
      <Field label="Music source dir" value={get(["music", "source_dir"])} onChange={(v) => setPath(["music", "source_dir"], v)} monospace />

      <button className="btn justify-center" onClick={() => setAdvanced((a) => !a)}>
        {advanced ? "Hide" : "Show"} advanced (full episode_defaults JSON — voices, characters)
      </button>
      {advanced && (
        <>
          <textarea
            className="input py-1.5"
            style={{ height: 220, resize: "vertical", whiteSpace: "pre", fontFamily: "inherit" }}
            value={advText}
            onChange={(e) => onAdv(e.target.value)}
          />
          {advErr && <span className="label-tiny text-red">JSON error: {advErr}</span>}
        </>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t hairline-soft sticky bottom-0 bg-bg-1 py-2">
        <button className="btn" onClick={onClose}>Close</button>
        <button className="btn btn-amber" disabled={busy || !!advErr} onClick={save}>Save</button>
      </div>
    </div>
  );
}

function Stub({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col gap-2 p-2">
      <div className="label-tiny">{title}</div>
      <p className="text-txt-dim text-[12px] leading-relaxed">{body}</p>
    </div>
  );
}
