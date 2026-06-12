import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { Field } from "./Field";
import { useStore } from "../store";
import { showsApi } from "../api/shows";
import { higgsfieldApi } from "../api/higgsfield";
import { THEMES, currentTheme, setTheme } from "../theme";
import { useT, LOCALES } from "../i18n";

type Tab = "theme" | "show" | "archive" | "git" | "comfy" | "higgsfield" | "language";

const TAB_IDS: Tab[] = ["theme", "show", "archive", "git", "comfy", "higgsfield", "language"];
const TAB_KEY: Record<Tab, string> = {
  theme: "settings.tabs.theme",
  show: "settings.tabs.show",
  archive: "settings.tabs.archive",
  git: "settings.tabs.git",
  comfy: "settings.tabs.comfy",
  higgsfield: "settings.tabs.higgsfield",
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
          {tab === "archive" && <ArchivePanel />}
          {tab === "git" && <Stub title={t("settings.tabs.git")} body={t("settings.git.stub")} />}
          {tab === "comfy" && <Stub title={t("settings.comfy.title")} body={t("settings.comfy.stub")} />}
          {tab === "higgsfield" && <HiggsfieldPanel />}
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

function ArchivePanel() {
  const t = useT();
  const qc = useQueryClient();
  const pushToast = useStore((s) => s.pushToast);
  const arch = useQuery({ queryKey: ["archive"], queryFn: showsApi.listArchive });
  const [busy, setBusy] = useState<string | null>(null);          // id currently restoring
  const [renaming, setRenaming] = useState<Record<string, string>>({}); // id → new slug input

  function refresh() {
    qc.invalidateQueries({ queryKey: ["archive"] });
    qc.invalidateQueries({ queryKey: ["episodes"] });
    qc.invalidateQueries({ queryKey: ["shows"] });
  }

  async function restoreEpisode(show: string, name: string, slug: string, newSlug?: string) {
    setBusy(name);
    try {
      const r = await showsApi.unarchiveEpisode(show, name, newSlug);
      pushToast(t("toast.episodeRestored", { slug: r.slug }), "ok");
      setRenaming((m) => { const n = { ...m }; delete n[name]; return n; });
      refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // 409 → the slug is taken by a live episode; reveal a rename field and retry.
      if (msg.startsWith("409")) {
        setRenaming((m) => ({ ...m, [name]: m[name] ?? `${slug}-restored` }));
        pushToast(t("settings.archive.slugTaken", { slug }), "err");
      } else {
        pushToast(`restore failed: ${msg}`, "err");
      }
    } finally { setBusy(null); }
  }

  async function restoreShow(name: string, label: string) {
    setBusy(name);
    try {
      await showsApi.unarchiveShow(name);
      pushToast(t("toast.showRestored", { show: label }), "ok");
      refresh();
    } catch (e) {
      pushToast(`restore failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setBusy(null); }
  }

  if (arch.isLoading) return <div className="text-txt-dim p-4">{t("common.loading")}</div>;
  if (arch.isError) return <div className="text-red p-4">{t("settings.archive.loadFail")}</div>;

  const epShows = Object.keys(arch.data?.episodes ?? {});
  const shows = arch.data?.shows ?? [];
  const empty = epShows.length === 0 && shows.length === 0;

  return (
    <div className="flex flex-col gap-3 max-h-[440px] overflow-y-auto pr-1">
      <div className="label-tiny">{t("settings.archive.title")}</div>
      <p className="label-tiny leading-relaxed">{t("settings.archive.help")}</p>

      {empty && <div className="label-tiny text-txt-dim py-2">{t("settings.archive.empty")}</div>}

      {shows.length > 0 && (
        <>
          <div className="label-tiny pt-1 border-t hairline-soft">{t("settings.archive.shows")}</div>
          {shows.map((s) => (
            <div key={s.name} className="flex items-center gap-2 px-2 py-1.5 rounded hairline-soft text-[12px]">
              <span className="truncate flex-1">{s.display_name}</span>
              <span className="label-tiny">{t("settings.archive.epCount", { n: s.episode_count })}</span>
              <button className="btn" disabled={busy === s.name}
                      onClick={() => restoreShow(s.name, s.display_name)}>
                {busy === s.name ? t("settings.archive.restoring") : t("settings.archive.restore")}
              </button>
            </div>
          ))}
        </>
      )}

      {epShows.map((sid) => (
        <div key={sid} className="flex flex-col gap-1">
          <div className="label-tiny pt-1 border-t hairline-soft">{t("settings.archive.episodesIn", { show: sid })}</div>
          {(arch.data?.episodes[sid] ?? []).map((ep) => (
            <div key={ep.name} className="flex flex-col gap-1 px-2 py-1.5 rounded hairline-soft">
              <div className="flex items-center gap-2 text-[12px]">
                <span className="font-mono">{ep.slug}</span>
                <span className="truncate flex-1 opacity-80">{ep.title}</span>
                {ep.variants.length > 0 && (
                  <span className="label-tiny">{t("settings.archive.variants", { n: ep.variants.length })}</span>
                )}
                <button className="btn" disabled={busy === ep.name}
                        onClick={() => restoreEpisode(ep.show, ep.name, ep.slug, renaming[ep.name])}>
                  {busy === ep.name ? t("settings.archive.restoring") : t("settings.archive.restore")}
                </button>
              </div>
              {renaming[ep.name] !== undefined && (
                <div className="flex items-center gap-2">
                  <input
                    className="input py-1 text-[11px] font-mono flex-1"
                    value={renaming[ep.name]}
                    placeholder={t("settings.archive.newSlugPh")}
                    onChange={(e) => setRenaming((m) => ({ ...m, [ep.name]: e.target.value }))}
                  />
                  <button className="btn btn-amber" disabled={busy === ep.name || !renaming[ep.name].trim()}
                          onClick={() => restoreEpisode(ep.show, ep.name, ep.slug, renaming[ep.name].trim())}>
                    {t("settings.archive.restoreAs")}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function HiggsfieldPanel() {
  const t = useT();
  const qc = useQueryClient();
  const pushToast = useStore((s) => s.pushToast);
  const auth = useQuery({ queryKey: ["hf-auth"], queryFn: higgsfieldApi.auth });

  const [handle, setHandle] = useState<string | null>(null);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteUrl, setPasteUrl] = useState("");
  const [busy, setBusy] = useState(false);

  // While a connect flow is pending, poll its status every 2s.
  useEffect(() => {
    if (!handle) return;
    const iv = setInterval(async () => {
      try {
        const p = await higgsfieldApi.authPoll(handle);
        if (p.status === "connected") {
          setHandle(null); setAuthUrl(null); setPasteOpen(false); setPasteUrl("");
          pushToast(t("settings.hf.connectedToast"), "ok");
          qc.invalidateQueries({ queryKey: ["hf-auth"] });
        } else if (p.status === "error") {
          setHandle(null); setAuthUrl(null);
          pushToast(t("settings.hf.connectFailed", { msg: p.error ?? "?" }), "err");
        }
      } catch { /* studio restarting etc — keep polling */ }
    }, 2000);
    return () => clearInterval(iv);
  }, [handle, qc, pushToast, t]);

  async function connect() {
    setBusy(true);
    try {
      const r = await higgsfieldApi.authStart();
      if (r.connected) {
        pushToast(t("settings.hf.connectedToast"), "ok");
        qc.invalidateQueries({ queryKey: ["hf-auth"] });
      } else if (r.auth_url) {
        setHandle(r.handle);
        setAuthUrl(r.auth_url);
        window.open(r.auth_url, "_blank", "noopener");
      }
    } catch (e) {
      pushToast(t("settings.hf.connectFailed", { msg: e instanceof Error ? e.message : String(e) }), "err");
    } finally { setBusy(false); }
  }

  async function submitPaste() {
    try {
      await higgsfieldApi.authManual(pasteUrl.trim());
      // poll loop picks up the resulting state change
    } catch (e) {
      pushToast(t("settings.hf.connectFailed", { msg: e instanceof Error ? e.message : String(e) }), "err");
    }
  }

  async function doDisconnect() {
    setBusy(true);
    try {
      await higgsfieldApi.disconnect();
      qc.invalidateQueries({ queryKey: ["hf-auth"] });
      pushToast(t("settings.hf.disconnected"), "ok");
    } catch (e) {
      pushToast(String(e), "err");
    } finally { setBusy(false); }
  }

  async function refreshModels() {
    setBusy(true);
    try {
      const m = await higgsfieldApi.models(true);
      qc.invalidateQueries({ queryKey: ["hf-models"] });
      pushToast(t("settings.hf.modelsRefreshed", { n: m.items.length }), "ok");
    } catch (e) {
      pushToast(String(e), "err");
    } finally { setBusy(false); }
  }

  if (auth.isLoading) return <div className="text-txt-dim p-4">{t("common.loading")}</div>;

  const a = auth.data;
  return (
    <div className="flex flex-col gap-3 max-h-[440px] overflow-y-auto pr-1">
      <div className="label-tiny">{t("settings.hf.title")}</div>
      <p className="label-tiny leading-relaxed">{t("settings.hf.help")}</p>

      {!a?.connected && (
        <>
          <button className="btn btn-amber justify-center" disabled={busy || !!handle} onClick={connect}>
            {handle ? t("settings.hf.waiting") : t("settings.hf.connect")}
          </button>
          {handle && authUrl && (
            <p className="label-tiny leading-relaxed">
              {t("settings.hf.openedTab")}{" "}
              <a className="underline" href={authUrl} target="_blank" rel="noopener noreferrer">
                {t("settings.hf.reopenLink")}
              </a>
            </p>
          )}
          {handle && (
            <>
              <button className="btn justify-center" onClick={() => setPasteOpen((o) => !o)}>
                {t("settings.hf.pasteToggle")}
              </button>
              {pasteOpen && (
                <div className="flex flex-col gap-2">
                  <p className="label-tiny leading-relaxed">{t("settings.hf.pasteHelp")}</p>
                  <input
                    className="input py-1 text-[11px] font-mono"
                    value={pasteUrl}
                    placeholder={t("settings.hf.pastePh")}
                    onChange={(e) => setPasteUrl(e.target.value)}
                  />
                  <button className="btn btn-amber justify-center" disabled={!pasteUrl.trim()} onClick={submitPaste}>
                    {t("settings.hf.pasteSubmit")}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {a?.connected && (
        <>
          <div className="flex items-center gap-2 px-3 py-2 rounded hairline-soft text-[12px]">
            <span className="rounded-full" style={{ width: 10, height: 10, background: "var(--green, #0c6)" }} />
            <span>{t("settings.hf.connected")}</span>
            {a.plan && <span className="label-tiny ml-auto uppercase">{t("settings.hf.plan", { plan: a.plan })}</span>}
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded hairline-soft text-[12px]">
            <span>{t("settings.hf.credits")}</span>
            <span className="font-mono ml-auto">{a.credits ?? "—"}</span>
          </div>
          {a.balance_error && <span className="label-tiny text-red">{a.balance_error}</span>}
          <div className="flex gap-2">
            <button className="btn flex-1 justify-center" disabled={busy}
                    onClick={() => qc.invalidateQueries({ queryKey: ["hf-auth"] })}>
              {t("settings.hf.refreshBalance")}
            </button>
            <button className="btn flex-1 justify-center" disabled={busy} onClick={refreshModels}>
              {t("settings.hf.refreshModels")}
            </button>
          </div>
          <HfModelBrowser />
          <div className="flex justify-end pt-2 border-t hairline-soft">
            <button className="btn" disabled={busy} onClick={doDisconnect}>{t("settings.hf.disconnect")}</button>
          </div>
        </>
      )}
    </div>
  );
}

function HfModelBrowser() {
  const t = useT();
  const models = useQuery({ queryKey: ["hf-models"], queryFn: () => higgsfieldApi.models(), staleTime: 3600_000, retry: false });
  // model id -> "12 cr / 5s" | "…" | "error"
  const [costs, setCosts] = useState<Record<string, string>>({});

  if (models.isLoading) return <div className="label-tiny text-txt-dim">{t("common.loading")}</div>;
  if (models.isError) return <div className="label-tiny text-red">{t("settings.hf.modelsFailed")}</div>;
  const items = models.data?.items ?? [];
  const groups: Array<["video" | "image" | "audio", string]> = [
    ["video", t("settings.hf.groupVideo")],
    ["image", t("settings.hf.groupImage")],
    ["audio", t("settings.hf.groupAudio")],
  ];

  const priceOf = async (id: string, dur?: number) => {
    setCosts((c) => ({ ...c, [id]: "…" }));
    try {
      const r = await higgsfieldApi.cost({ model: id, ...(dur ? { duration: dur } : {}) });
      setCosts((c) => ({
        ...c,
        [id]: r.credits == null
          ? t("settings.hf.costUnknown")
          : dur ? t("settings.hf.costPerClip", { n: r.credits, s: dur }) : t("settings.hf.costPerImage", { n: r.credits }),
      }));
    } catch {
      setCosts((c) => ({ ...c, [id]: t("settings.hf.costUnknown") }));
    }
  };

  return (
    <div className="flex flex-col gap-1 pt-2 border-t hairline-soft">
      <div className="label-tiny">{t("settings.hf.modelsTitle")}</div>
      <p className="label-tiny leading-relaxed">{t("settings.hf.modelsHelp")}</p>
      {groups.map(([type, label]) => {
        const list = items.filter((m) => m.output_type === type);
        if (!list.length) return null;
        return (
          <div key={type} className="flex flex-col gap-1">
            <div className="label-tiny pt-1">{label}</div>
            {list.map((m) => {
              const durs = m.durations?.length
                ? m.durations.join("/") + "s"
                : m.duration_range ? `${m.duration_range.min}–${m.duration_range.max}s` : null;
              const defDur = m.output_type === "video"
                ? (m.durations?.[0] ?? m.duration_range?.min ?? 5) : undefined;
              const lipsync = (m.medias ?? []).some((md) => (md.roles ?? []).includes("audio"));
              return (
                <div key={m.id} className="flex items-start gap-2 px-2 py-1.5 rounded hairline-soft text-[12px]">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate">{m.name}</span>
                      <span className="label-tiny text-txt-faint">{m.provider_name}</span>
                      {lipsync && m.output_type === "video" && <span title={t("settings.hf.lipsyncCapable")}>👄</span>}
                    </div>
                    <div className="label-tiny font-mono truncate" title={m.description}>{m.id}</div>
                    <div className="label-tiny text-txt-faint">
                      {[durs, m.aspect_ratios?.length ? m.aspect_ratios.join(" ") : null].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 flex-none">
                    {costs[m.id]
                      ? <span className="font-mono text-[11px]">{costs[m.id]}</span>
                      : <button className="btn text-[10px] px-1.5 py-0.5" onClick={() => priceOf(m.id, defDur)}>
                          {t("settings.hf.checkCost")}
                        </button>}
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
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
