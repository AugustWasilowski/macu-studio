import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { IChevron } from "./Icons";
import { Modal } from "./Modal";
import { Field } from "./Field";
import { useStore } from "../store";
import { showsApi, exportUrl, cloneVoiceRef } from "../api/shows";
import { macuWeb } from "../api/macuweb";
import { api } from "../api";
import { WIZARD_STEPS } from "../wizard/wizard";
import { STARTER_SLUG } from "../wizard/starterScript";
import type { Route } from "../route";
import { useT } from "../i18n";
import { Trans } from "../i18n/Trans";

interface Props {
  activeShow: string;
  slug: string;
  go: (r: Partial<Route>) => void;
  onOpenSettings: () => void;
  onStartTutorial: () => void;
  onGoAssembly: () => void;
}

type Dialog = null | "new-show" | "new-episode" | "export" | "macu-web" | "shutdown";

export function FileMenu({ activeShow, slug, go, onOpenSettings, onStartTutorial, onGoAssembly }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [cloneVoices, setCloneVoices] = useState<{ show: string; names: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const setActiveShow = useStore((s) => s.setActiveShow);
  const pushToast = useStore((s) => s.pushToast);
  const openUpdate = useStore((s) => s.openUpdate);
  const openDiagnostics = useStore((s) => s.openDiagnostics);
  const wizard = useStore((s) => s.wizard);
  const startWizard = useStore((s) => s.startWizard);
  const setWizardStep = useStore((s) => s.setWizardStep);
  const qc = useQueryClient();

  // Resume a paused/active walkthrough where it left off; otherwise start a fresh one.
  function startOrResumeWizard() {
    if (wizard && (wizard.status === "paused" || wizard.status === "active")) setWizardStep(wizard.step);
    else startWizard(STARTER_SLUG);
  }
  const resumable = wizard?.status === "paused";

  const shows = useQuery({ queryKey: ["shows"], queryFn: showsApi.list, enabled: open });
  const curShow = shows.data?.shows.find((s) => s.id === activeShow);

  function close() { setOpen(false); }

  function openShow(id: string) {
    setActiveShow(id);
    qc.invalidateQueries({ queryKey: ["episodes"] });
    go({ page: "stage", slug: "", stage: "assembly" }); // empty slug → default-pick effect
    close();
  }

  async function onImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    pushToast(t("toast.importing", { name: f.name }), "run");
    try {
      const r = await showsApi.importZip(f);
      const bits = [
        r.created.length ? t("filemenu.importBitNew", { n: r.created.length }) : "",
        r.updated.length ? t("filemenu.importBitUpdated", { n: r.updated.length }) : "",
        r.templates?.length ? t("filemenu.importBitTemplates", { count: r.templates.length }) : "",
        r.voices?.length ? t("filemenu.importBitVoices", { count: r.voices.length }) : "",
        r.sfx?.length ? t("filemenu.importBitSfx", { n: r.sfx.length }) : "",
        r.music?.length ? t("filemenu.importBitMusic", { n: r.music.length }) : "",
        r.created_show ? t("filemenu.importBitShowCreated", { show: r.show }) : "",
      ].filter(Boolean).join(", ");
      pushToast(t("toast.importDone", { show: r.show, bits: bits || t("filemenu.importNoEpisodes") }), r.errors.length ? "info" : "ok");
      r.errors.forEach((err) => pushToast(`import: ${err}`, "err"));
      qc.invalidateQueries({ queryKey: ["episodes"] });
      qc.invalidateQueries({ queryKey: ["shows"] });
      // Jump to the script page of the first imported episode (sorted → ep-001 of
      // a season, or the lone episode of a single-episode import).
      const imported = [...r.created, ...r.updated].sort();
      if (imported.length) {
        setActiveShow(r.show);
        go({ page: "stage", slug: imported[0], stage: "script" });
      }
      // Voices arrive as reference clips — offer the optional GPU re-clone step.
      if (r.voices?.length) setCloneVoices({ show: r.show, names: r.voices });
    } catch (err) {
      pushToast(`import failed: ${err instanceof Error ? err.message : String(err)}`, "err");
    }
  }

  const Item = ({ label, onClick, hint }: { label: string; onClick: () => void; hint?: string }) => (
    <button
      className="w-full flex items-center justify-between px-3 py-1.5 text-left hover:bg-bg-3 text-[12px]"
      onClick={() => { close(); onClick(); }}
    >
      <span>{label}</span>
      {hint && <span className="label-tiny">{hint}</span>}
    </button>
  );
  const Section = ({ label }: { label: string }) => (
    <div className="label-tiny px-3 pt-2 pb-1 border-t hairline-soft mt-1 first:mt-0 first:border-0">{label}</div>
  );

  return (
    <div className="relative" data-tour="file-menu">
      <button
        className="panel-title hover:brightness-125 cursor-pointer flex items-center gap-1"
        onClick={() => setOpen((o) => !o)}
        title={t("filemenu.menuTitle")}
      >
        MACU STUDIO
        <IChevron size={12} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={close} />
          <div className="absolute top-[26px] left-0 z-50 panel w-[260px] py-1">
            <Section label={t("filemenu.sectionShow")} />
            <div className="px-3 py-1 text-[12px] text-amber font-bold truncate">
              {curShow?.name ?? activeShow}
            </div>
            {(shows.data?.shows.length ?? 0) > 1 && (
              <div className="max-h-[160px] overflow-y-auto">
                {shows.data!.shows.filter((s) => s.id !== activeShow).map((s) => (
                  <button
                    key={s.id}
                    className="w-full flex items-center justify-between px-3 py-1.5 text-left hover:bg-bg-3 text-[12px]"
                    onClick={() => openShow(s.id)}
                  >
                    <span className="truncate">{s.name}</span>
                    <span className="label-tiny">{s.episode_count} ep</span>
                  </button>
                ))}
              </div>
            )}
            <Item label={t("filemenu.newShow")} onClick={() => setDialog("new-show")} />

            <Section label={t("filemenu.sectionEpisode")} />
            <Item label={t("filemenu.newEpisode")} onClick={() => setDialog("new-episode")} />

            <Section label={t("filemenu.sectionProject")} />
            <Item label={t("filemenu.import")} onClick={() => fileRef.current?.click()} hint=".zip" />
            <Item label={t("filemenu.export")} onClick={() => setDialog("export")} />
            <Item label={t("filemenu.macuWebItem")} onClick={() => setDialog("macu-web")} hint="↗" />

            <Section label={t("filemenu.sectionLearn")} />
            <Item label={t("filemenu.tutorial")} onClick={onStartTutorial} />
            <Item
              label={resumable ? t("filemenu.resumeWalkthrough", { n: wizard!.step + 1, total: WIZARD_STEPS.length }) : t("filemenu.walkthrough")}
              onClick={startOrResumeWizard}
            />
            <Item label={t("filemenu.visitMacuWeb")} onClick={() => window.open("https://mayorawesome.com", "_blank", "noopener,noreferrer")} hint="↗" />

            <Section label={t("filemenu.sectionMore")} />
            <Item label={t("filemenu.settings")} onClick={onOpenSettings} />
            <Item label={t("filemenu.checkUpdates")} onClick={openUpdate} />
            <Item label={t("filemenu.runDiagnostics")} onClick={openDiagnostics} />
            <Item label={t("filemenu.goToAssembly")} onClick={onGoAssembly} />
            <Item label={t("filemenu.shutDown")} onClick={() => setDialog("shutdown")} />
          </div>
        </>
      )}

      <input ref={fileRef} type="file" accept=".zip" className="hidden" onChange={onImportFile} />

      {dialog === "new-show" && (
        <NewShowDialog
          onClose={() => setDialog(null)}
          onCreated={(id) => { setDialog(null); qc.invalidateQueries({ queryKey: ["shows"] }); openShow(id); }}
        />
      )}
      {dialog === "new-episode" && (
        <NewEpisodeDialog
          show={activeShow}
          onClose={() => setDialog(null)}
          onCreated={(s) => { setDialog(null); qc.invalidateQueries({ queryKey: ["episodes"] }); go({ page: "stage", slug: s, stage: "script" }); }}
        />
      )}
      {dialog === "export" && (
        <ExportDialog show={activeShow} slug={slug} onClose={() => setDialog(null)} />
      )}
      {dialog === "macu-web" && (
        <MacuWebDialog show={activeShow} onClose={() => setDialog(null)} />
      )}
      {dialog === "shutdown" && <ShutdownDialog onClose={() => setDialog(null)} />}
      {cloneVoices && (
        <CloneVoicesModal show={cloneVoices.show} names={cloneVoices.names} onClose={() => setCloneVoices(null)} />
      )}
    </div>
  );
}

function CloneVoicesModal({ show, names, onClose }: { show: string; names: string[]; onClose: () => void }) {
  const t = useT();
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(0);
  const [current, setCurrent] = useState<string | null>(null);
  const [failed, setFailed] = useState<string[]>([]);
  const [finished, setFinished] = useState(false);
  const pushToast = useStore((s) => s.pushToast);

  async function run() {
    setRunning(true);
    const fails: string[] = [];
    for (const name of names) {
      setCurrent(name);
      try {
        await cloneVoiceRef(name, show);
      } catch {
        fails.push(name);
      }
      setDone((d) => d + 1);
    }
    setCurrent(null);
    setFailed(fails);
    setFinished(true);
    setRunning(false);
    pushToast(
      fails.length
        ? t("toast.clonedPartial", { cloned: names.length - fails.length, total: names.length, failed: fails.length })
        : t("toast.clonedAll", { count: names.length }),
      fails.length ? "err" : "ok",
    );
  }

  const pct = names.length ? Math.round((done / names.length) * 100) : 0;

  return (
    <Modal
      open
      onClose={running ? () => {} : onClose}
      title={t("filemenu.cloneVoicesTitle")}
      width={460}
      footer={running ? undefined : finished ? (
        <button className="btn btn-amber" onClick={onClose}>{t("common.close")}</button>
      ) : (
        <>
          <button className="btn" onClick={onClose}>{t("common.later")}</button>
          <button className="btn btn-amber" onClick={run}>{t("filemenu.cloneVoicesBtn", { count: names.length })}</button>
        </>
      )}
    >
      {!finished ? (
        <div className="flex flex-col gap-3">
          <p className="label-tiny leading-relaxed">
            {t("filemenu.cloneVoicesBody", { count: names.length, show, n: names.length })}
          </p>
          <div className="flex flex-wrap gap-1">
            {names.map((n) => <span key={n} className="label-tiny px-1.5 py-0.5 bg-bg-3 rounded">{n}</span>)}
          </div>
          {running && (
            <div className="flex flex-col gap-1">
              <div className="h-2 bg-bg-3 rounded overflow-hidden">
                <div className="h-full bg-amber transition-all" style={{ width: `${pct}%` }} />
              </div>
              <div className="label-tiny">{t("filemenu.cloneVoicesProgress", { done, total: names.length, current: current ?? "…" })}</div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2 py-1">
          <div className="text-[13px]">{t("filemenu.cloneVoicesDone", { cloned: names.length - failed.length, total: names.length })}</div>
          {failed.length > 0 && (
            <p className="label-tiny text-err leading-relaxed">
              {t("filemenu.cloneVoicesFailed", { names: failed.join(", ") })}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}

function MacuWebDialog({ show, onClose }: { show: string; onClose: () => void }) {
  const t = useT();
  const pushToast = useStore((s) => s.pushToast);
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [vids, setVids] = useState<Record<string, string>>({}); // per-slug video-id overrides

  const status = useQuery({ queryKey: ["macu-web-status"], queryFn: macuWeb.status });
  const connected = !!status.data?.connected;
  const eps = useQuery({
    queryKey: ["episodes", show],
    queryFn: () => api.episodes(show),
    enabled: connected,
  });

  async function connect() {
    setConnecting(true);
    try {
      const r = await macuWeb.connect(token.trim());
      pushToast(t("toast.macuWebConnected", { base: r.base }), "ok");
      setToken("");
      qc.invalidateQueries({ queryKey: ["macu-web-status"] });
    } catch (e) {
      pushToast(`connect failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setConnecting(false); }
  }

  async function toggle(slug: string, published: boolean) {
    try {
      await macuWeb.setPublished(slug, published);
      qc.invalidateQueries({ queryKey: ["episodes", show] });
      qc.invalidateQueries({ queryKey: ["episodes"] });
    } catch (e) {
      pushToast(`${slug}: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }

  async function saveVid(slug: string, raw: string, current: string) {
    if ((raw ?? "").trim() === (current ?? "").trim()) return; // no change
    try {
      const r = await macuWeb.setVideoId(slug, raw.trim());
      setVids((v) => ({ ...v, [slug]: r.video_id ?? "" }));
      pushToast(r.video_id ? `${slug}: video set (${r.video_id})` : `${slug}: video cleared`, "ok");
      qc.invalidateQueries({ queryKey: ["episodes", show] });
    } catch (e) {
      pushToast(`${slug}: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }

  async function publish() {
    setPublishing(true);
    try {
      const r = await macuWeb.publish(show);
      pushToast(
        r.pushed
          ? t("toast.macuWebPublished", { show, files: r.files })
          : t("toast.macuWebCommitted", { files: r.files }),
        r.pushed ? "ok" : "info",
      );
    } catch (e) {
      pushToast(`publish failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setPublishing(false); }
  }

  return (
    <Modal
      open onClose={onClose} title={t("filemenu.macuWebTitle")} width={520}
      footer={connected ? (
        <>
          <button className="btn" onClick={onClose}>{t("common.close")}</button>
          <button className="btn btn-amber" disabled={publishing} onClick={publish}>
            {publishing ? t("filemenu.macuWebPublishingBtn") : t("filemenu.macuWebPublishBtn", { show })}
          </button>
        </>
      ) : undefined}
    >
      {!connected ? (
        <div className="flex flex-col gap-3">
          <p className="label-tiny leading-relaxed">
            {t("filemenu.macuWebConnectHint")}
          </p>
          <textarea
            className="w-full bg-bg-2 rounded px-2 py-1.5 text-[12px] font-mono hairline"
            value={token} onChange={(e) => setToken(e.target.value)}
            placeholder="macu-connect.…" rows={3}
          />
          <button className="btn btn-amber justify-center" disabled={connecting || !token.trim()} onClick={connect}>
            {connecting ? t("filemenu.macuWebConnectingBtn") : t("filemenu.macuWebConnectBtn")}
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="label-tiny leading-relaxed">
            <Trans
              k="filemenu.macuWebConnectedHint"
              vars={{ base: status.data?.base ?? "" }}
              tags={[(c) => <span className="font-mono">{c}</span>]}
            />
          </p>
          <div className="flex flex-col gap-0.5 max-h-[320px] overflow-y-auto">
            {eps.data?.episodes.length === 0 && <div className="label-tiny">{t("filemenu.macuWebNoEpisodes")}</div>}
            {eps.data?.episodes.map((ep) => {
              const vid = vids[ep.slug] !== undefined ? vids[ep.slug] : (ep.youtube_id ?? "");
              return (
                <div key={ep.slug} className="flex items-center gap-2 text-[12px] py-1 px-1 hover:bg-bg-3 rounded">
                  <input
                    type="checkbox" checked={!!ep.published}
                    onChange={(e) => toggle(ep.slug, e.target.checked)}
                    title="Public on MACU Web"
                  />
                  <span className="font-mono">{ep.slug}</span>
                  <span className="truncate flex-1 opacity-80">{ep.title}</span>
                  {ep.se_label && <span className="label-tiny">{ep.se_label}</span>}
                  <input
                    className="bg-bg-2 rounded px-1.5 py-0.5 text-[11px] font-mono hairline w-[140px]"
                    placeholder="YouTube ID / URL"
                    title="YouTube video id or URL — paste a link; Publish to push"
                    value={vid}
                    onChange={(e) => setVids((v) => ({ ...v, [ep.slug]: e.target.value }))}
                    onBlur={(e) => saveVid(ep.slug, e.target.value, ep.youtube_id ?? "")}
                    onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Modal>
  );
}

function ShutdownDialog({ onClose }: { onClose: () => void }) {
  const t = useT();
  const [shutting, setShutting] = useState(false);

  async function go() {
    setShutting(true);
    try { await api.shutdown(); } catch { /* the server is going down — the request may not finish */ }
  }

  return (
    <Modal
      open
      // Always allow the X / Esc / backdrop to dismiss — even mid-shutdown. The real
      // server may already be gone (closing just reveals the frozen app, harmless), and
      // if the shutdown is a no-op (e.g. the demo) this is the only escape from a soft-lock.
      onClose={onClose}
      title={t("filemenu.shutdownTitle")}
      width={440}
      footer={shutting ? undefined : (
        <>
          <button className="btn" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={go}>{t("filemenu.shutdownBtn")}</button>
        </>
      )}
    >
      {!shutting ? (
        <p className="label-tiny leading-relaxed">
          <Trans
            k="filemenu.shutdownBody"
            vars={{ cmd: "./deploy/start-studio.sh" }}
            tags={[(c) => <span className="font-mono">{c}</span>]}
          />
        </p>
      ) : (
        <div className="flex flex-col gap-2 py-1">
          <div className="text-amber text-[13px]">{t("filemenu.shuttingDown")}</div>
          <p className="label-tiny leading-relaxed">
            {t("filemenu.shuttingDownBody")}
          </p>
        </div>
      )}
    </Modal>
  );
}

function NewShowDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const t = useT();
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [busy, setBusy] = useState(false);
  const pushToast = useStore((s) => s.pushToast);
  // Auto-slug from name until the user edits the id.
  const [idTouched, setIdTouched] = useState(false);
  const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
  const effId = idTouched ? id : slugify(name);

  async function create() {
    setBusy(true);
    try {
      await showsApi.create(effId, name);
      pushToast(t("toast.showCreated", { id: effId }), "ok");
      onCreated(effId);
    } catch (e) {
      pushToast(`create show failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setBusy(false); }
  }

  return (
    <Modal
      open onClose={onClose} title={t("filemenu.newShowTitle")} width={440}
      footer={<>
        <button className="btn" onClick={onClose}>{t("common.cancel")}</button>
        <button className="btn btn-amber" disabled={busy || !effId} onClick={create}>{t("common.create")}</button>
      </>}
    >
      <div className="flex flex-col gap-3">
        <Field label={t("filemenu.newShowFieldName")} value={name} onChange={setName} placeholder={t("filemenu.newShowPlaceholderName")} />
        <Field label={t("filemenu.newShowFieldId")} value={effId}
               onChange={(v) => { setIdTouched(true); setId(v); }} placeholder={t("filemenu.newShowPlaceholderId")} />
        <p className="label-tiny leading-relaxed">
          {t("filemenu.newShowHint")}
        </p>
      </div>
    </Modal>
  );
}

function NewEpisodeDialog({ show, onClose, onCreated }: { show: string; onClose: () => void; onCreated: (slug: string) => void }) {
  const t = useT();
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const pushToast = useStore((s) => s.pushToast);

  async function create() {
    setBusy(true);
    try {
      const r = await showsApi.createEpisode(show, slug, title);
      pushToast(t("toast.episodeCreated", { slug: r.slug }), "ok");
      onCreated(r.slug);
    } catch (e) {
      pushToast(`create episode failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setBusy(false); }
  }

  return (
    <Modal
      open onClose={onClose} title={t("filemenu.newEpisodeTitle", { show })} width={440}
      footer={<>
        <button className="btn" onClick={onClose}>{t("common.cancel")}</button>
        <button className="btn btn-amber" disabled={busy || !slug} onClick={create}>{t("common.create")}</button>
      </>}
    >
      <div className="flex flex-col gap-3">
        <Field label={t("filemenu.newEpisodeFieldSlug")} value={slug} onChange={setSlug} placeholder={t("filemenu.newEpisodePlaceholderSlug")} />
        <Field label={t("filemenu.newEpisodeFieldTitle")} value={title} onChange={setTitle} placeholder={t("filemenu.newEpisodePlaceholderTitle")} />
        <p className="label-tiny leading-relaxed">
          {t("filemenu.newEpisodeHint")}
        </p>
      </div>
    </Modal>
  );
}

function ExportDialog({ show, slug, onClose }: { show: string; slug: string; onClose: () => void }) {
  const t = useT();
  const [withAssets, setWithAssets] = useState(true);
  function dl(url: string) {
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
    onClose();
  }
  return (
    <Modal open onClose={onClose} title={t("filemenu.exportTitle")} width={440}>
      <div className="flex flex-col gap-2">
        <p className="label-tiny leading-relaxed">
          {t("filemenu.exportBody")}
        </p>
        <label className="flex items-center gap-2 text-[12px] cursor-pointer select-none py-1">
          <input type="checkbox" checked={withAssets} onChange={(e) => setWithAssets(e.target.checked)} />
          {t("filemenu.exportAssetsCheckbox")}
        </label>
        <button className="btn btn-amber justify-center" disabled={!slug} onClick={() => dl(exportUrl.episode(slug, withAssets))}>
          {t("filemenu.exportEpisodeBtn", { slug: slug || "—" })}
        </button>
        <button className="btn justify-center" onClick={() => dl(exportUrl.show(show, withAssets))}>
          {t("filemenu.exportShowBtn", { show })}
        </button>
        <button className="btn justify-center" onClick={() => dl(exportUrl.voicesAll())}>
          {t("filemenu.exportAllVoicesBtn")}
        </button>
        <p className="label-tiny leading-relaxed opacity-70">
          {t("filemenu.exportVoiceHint")}
        </p>
      </div>
    </Modal>
  );
}
