import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { Field } from "./Field";
import { useStore } from "../store";
import { showsApi } from "../api/shows";
import { THEMES, currentTheme, setTheme } from "../theme";
import { useT, LOCALES } from "../i18n";

type Tab = "theme" | "show" | "git" | "comfy" | "language";

const TAB_IDS: Tab[] = ["theme", "show", "git", "comfy", "language"];
const TAB_KEY: Record<Tab, string> = {
  theme: "settings.tabs.theme",
  show: "settings.tabs.show",
  git: "settings.tabs.git",
  comfy: "settings.tabs.comfy",
  language: "settings.tabs.language",
};

export function Settings({ show, onClose }: { show: string; onClose: () => void }) {
  const t = useT();
  const [tab, setTab] = useState<Tab>("theme");
  return (
    <Modal open onClose={onClose} title={t("settings.title")} width={680}>
      <div className="flex gap-3 min-h-[320px]">
        <div className="flex flex-col gap-1 w-[150px] shrink-0 border-r hairline-soft pr-2">
          {TAB_IDS.map((id) => (
            <button
              key={id}
              className={"text-left px-2 py-1.5 rounded text-[12px] " + (tab === id ? "btn-amber" : "hover:bg-bg-3")}
              onClick={() => setTab(id)}
            >
              {t(TAB_KEY[id])}
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-0">
          {tab === "theme" && <ThemePanel />}
          {tab === "language" && <LanguagePanel />}
          {tab === "show" && <ShowPanel show={show} onClose={onClose} />}
          {tab === "git" && <Stub title={t("settings.tabs.git")} body={t("settings.git.stub")} />}
          {tab === "comfy" && <Stub title={t("settings.comfy.title")} body={t("settings.comfy.stub")} />}
        </div>
      </div>
    </Modal>
  );
}

function ThemePanel() {
  const t = useT();
  const [sel, setSel] = useState(currentTheme());
  const accents = THEMES.filter((th) => th.kind === "accent");
  const fulls = THEMES.filter((th) => th.kind === "full");
  const activeAccent = accents.find((a) => a.id === sel);
  const pick = (id: string) => { setTheme(id); setSel(id); };
  return (
    <div className="flex flex-col gap-3">
      <div className="label-tiny">{t("settings.theme.title")}</div>
      <p className="label-tiny leading-relaxed">{t("settings.theme.help")}</p>
      <div className="flex flex-col gap-2">
        {/* The five accent presets live in ONE "Terminal" row — pick the color
            by clicking its dot. (Theme names stay untranslated by design.) */}
        <div className={"flex items-center gap-3 px-3 py-2 rounded hairline-soft " + (activeAccent ? "btn-amber" : "")}>
          <span className="flex items-center gap-2">
            {accents.map((a) => (
              <button
                key={a.id}
                title={a.label}
                aria-label={a.label}
                onClick={() => pick(a.id)}
                className="rounded-full"
                style={{
                  width: 16, height: 16, background: a.accent, flexShrink: 0,
                  transition: "transform 0.15s ease, box-shadow 0.15s ease",
                  transform: sel === a.id ? "scale(1.2)" : undefined,
                  boxShadow: sel === a.id
                    ? `0 0 0 2px var(--bg-1), 0 0 0 3.5px ${a.accent}, 0 0 8px ${a.accent}`
                    : undefined,
                }}
              />
            ))}
          </span>
          <span className="text-[12px]">Terminal</span>
          {activeAccent && <span className="label-tiny ml-auto">{t("common.active")} · {activeAccent.label}</span>}
        </div>
        {fulls.map((th) => (
          <button
            key={th.id}
            className={"flex items-center gap-3 px-3 py-2 rounded hairline-soft text-left " + (sel === th.id ? "btn-amber" : "hover:bg-bg-3")}
            onClick={() => pick(th.id)}
          >
            <span className="flex items-center gap-1">
              {(th.swatch ?? [th.accent]).map((c, i) => (
                <span key={i} className="rounded-full" style={{ width: 16, height: 16, background: c, boxShadow: i === 0 ? `0 0 7px ${c}` : undefined }} />
              ))}
            </span>
            <span className="text-[12px]">{th.label}</span>
            {sel === th.id && <span className="label-tiny ml-auto">{t("common.active")}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function LanguagePanel() {
  const t = useT();
  const locale = useStore((s) => s.locale);
  const setLocale = useStore((s) => s.setLocale);
  return (
    <div className="flex flex-col gap-3 max-h-[440px] overflow-y-auto pr-1">
      <div className="label-tiny">{t("settings.lang.title")}</div>
      <p className="label-tiny leading-relaxed">{t("settings.lang.help")}</p>
      <div className="flex flex-col gap-2">
        {LOCALES.map((l) => (
          <button
            key={l.code}
            dir={l.dir}
            className={"flex items-center gap-3 px-3 py-2 rounded hairline-soft text-left " + (locale === l.code ? "btn-amber" : "hover:bg-bg-3")}
            onClick={() => setLocale(l.code)}
          >
            <span className="text-[12px]">{l.nativeName}</span>
            <span className="label-tiny text-txt-dim">{l.englishName}</span>
            {l.completeness < 1 && (
              <span className="label-tiny text-amber">{t("settings.lang.partial", { pct: Math.round(l.completeness * 100) })}</span>
            )}
            {locale === l.code && <span className="label-tiny ml-auto">{t("common.active")}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

function ShowPanel({ show, onClose }: { show: string; onClose: () => void }) {
  const t = useT();
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
    if (advErr) { pushToast(t("toast.fixJson"), "err"); return; }
    setBusy(true);
    try {
      await showsApi.putConfig(show, { name, title_prefix: prefix, assets_dir: assets, episode_defaults: defaults });
      pushToast(t("toast.showSaved", { show }), "ok");
      qc.invalidateQueries({ queryKey: ["show-config", show] });
      qc.invalidateQueries({ queryKey: ["shows"] });
    } catch (e) {
      pushToast(t("toast.saveFailed", { msg: e instanceof Error ? e.message : String(e) }), "err");
    } finally { setBusy(false); }
  }

  if (cfg.isLoading) return <div className="text-txt-dim p-4">{t("common.loading")}</div>;
  if (cfg.isError) return <div className="text-red p-4">{t("settings.show.loadFail")}</div>;

  return (
    <div className="flex flex-col gap-3 max-h-[440px] overflow-y-auto pr-1">
      <div className="label-tiny">{show}{cfg.data?.id === "the-macu-report" ? t("settings.show.defaultSuffix") : ""}</div>
      <Field label={t("settings.show.name")} value={name} onChange={setName} />
      <Field label={t("settings.show.prefix")} value={prefix} onChange={setPrefix} placeholder={t("settings.show.prefixPh")} />
      <Field label={t("settings.show.assets")} value={assets} onChange={setAssets} monospace />
      <div className="label-tiny pt-1 border-t hairline-soft">{t("settings.show.defaults")}</div>
      <Field label={t("settings.show.styleSuffix")} value={get(["style", "suffix"])} onChange={(v) => setPath(["style", "suffix"], v)} rows={3} />
      <Field label={t("settings.show.styleNegative")} value={get(["style", "negative"])} onChange={(v) => setPath(["style", "negative"], v)} rows={3} />
      <Field label={t("settings.show.checkpoint")} value={get(["comfyui", "checkpoint"])} onChange={(v) => setPath(["comfyui", "checkpoint"], v)} />
      <Field label={t("settings.show.musicDir")} value={get(["music", "source_dir"])} onChange={(v) => setPath(["music", "source_dir"], v)} monospace />

      <button className="btn justify-center" onClick={() => setAdvanced((a) => !a)}>
        {t("settings.show.advanced", { action: advanced ? t("common.hide") : t("common.show") })}
      </button>
      {advanced && (
        <>
          <textarea
            className="input py-1.5"
            style={{ height: 220, resize: "vertical", whiteSpace: "pre", fontFamily: "inherit" }}
            value={advText}
            onChange={(e) => onAdv(e.target.value)}
          />
          {advErr && <span className="label-tiny text-red">{t("settings.show.jsonError", { msg: advErr })}</span>}
        </>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t hairline-soft sticky bottom-0 bg-bg-1 py-2">
        <button className="btn" onClick={onClose}>{t("common.close")}</button>
        <button className="btn btn-amber" disabled={busy || !!advErr} onClick={save}>{t("common.save")}</button>
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
