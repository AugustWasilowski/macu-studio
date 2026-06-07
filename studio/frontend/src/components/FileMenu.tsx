import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { IChevron } from "./Icons";
import { Modal } from "./Modal";
import { Field } from "./Field";
import { useStore } from "../store";
import { showsApi, exportUrl, cloneVoiceRef } from "../api/shows";
import { api } from "../api";
import type { Route } from "../route";

interface Props {
  activeShow: string;
  slug: string;
  go: (r: Partial<Route>) => void;
  onOpenSettings: () => void;
  onStartTutorial: () => void;
  onGoAssembly: () => void;
}

type Dialog = null | "new-show" | "new-episode" | "export" | "shutdown";

export function FileMenu({ activeShow, slug, go, onOpenSettings, onStartTutorial, onGoAssembly }: Props) {
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [cloneVoices, setCloneVoices] = useState<{ show: string; names: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const setActiveShow = useStore((s) => s.setActiveShow);
  const pushToast = useStore((s) => s.pushToast);
  const qc = useQueryClient();

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
    pushToast(`importing ${f.name}…`, "run");
    try {
      const r = await showsApi.importZip(f);
      const bits = [
        r.created.length ? `${r.created.length} new` : "",
        r.updated.length ? `${r.updated.length} updated` : "",
        r.templates?.length ? `${r.templates.length} template${r.templates.length > 1 ? "s" : ""}` : "",
        r.voices?.length ? `${r.voices.length} voice${r.voices.length > 1 ? "s" : ""}` : "",
        r.created_show ? `show '${r.show}' created` : "",
      ].filter(Boolean).join(", ");
      pushToast(`import → ${r.show}: ${bits || "no episodes"}`, r.errors.length ? "info" : "ok");
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
        title="Project menu"
      >
        MACU STUDIO
        <IChevron size={12} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={close} />
          <div className="absolute top-[26px] left-0 z-50 panel w-[260px] py-1">
            <Section label="Show" />
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
            <Item label="New show…" onClick={() => setDialog("new-show")} />

            <Section label="Episode" />
            <Item label="New episode…" onClick={() => setDialog("new-episode")} />

            <Section label="Project" />
            <Item label="Import…" onClick={() => fileRef.current?.click()} hint=".zip" />
            <Item label="Export…" onClick={() => setDialog("export")} />

            <Section label="More" />
            <Item label="Settings…" onClick={onOpenSettings} />
            <Item label="Tutorial" onClick={onStartTutorial} />
            <Item label="Go to Assembly" onClick={onGoAssembly} />
            <Item label="Shut down Studio…" onClick={() => setDialog("shutdown")} />
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
      {dialog === "shutdown" && <ShutdownDialog onClose={() => setDialog(null)} />}
      {cloneVoices && (
        <CloneVoicesModal show={cloneVoices.show} names={cloneVoices.names} onClose={() => setCloneVoices(null)} />
      )}
    </div>
  );
}

function CloneVoicesModal({ show, names, onClose }: { show: string; names: string[]; onClose: () => void }) {
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
      fails.length ? `cloned ${names.length - fails.length}/${names.length} voices (${fails.length} failed)`
                   : `cloned ${names.length} voice${names.length > 1 ? "s" : ""}`,
      fails.length ? "err" : "ok",
    );
  }

  const pct = names.length ? Math.round((done / names.length) * 100) : 0;

  return (
    <Modal
      open
      onClose={running ? () => {} : onClose}
      title="Import voices"
      width={460}
      footer={running ? undefined : finished ? (
        <button className="btn btn-amber" onClick={onClose}>Close</button>
      ) : (
        <>
          <button className="btn" onClick={onClose}>Later</button>
          <button className="btn btn-amber" onClick={run}>Clone {names.length} voice{names.length > 1 ? "s" : ""}</button>
        </>
      )}
    >
      {!finished ? (
        <div className="flex flex-col gap-3">
          <p className="label-tiny leading-relaxed">
            This import brought <span className="text-amber">{names.length}</span> voice
            {names.length > 1 ? "s" : ""} as reference clips. Re-cloning rebuilds them in
            this machine's OmniVoice and re-points <span className="font-mono">{show}</span>'s
            speakers at them. <span className="text-amber">It starts OmniVoice and uses the GPU</span>
            {" "}(~a few seconds per voice). You can do it later from the voice picker.
          </p>
          <div className="flex flex-wrap gap-1">
            {names.map((n) => <span key={n} className="label-tiny px-1.5 py-0.5 bg-bg-3 rounded">{n}</span>)}
          </div>
          {running && (
            <div className="flex flex-col gap-1">
              <div className="h-2 bg-bg-3 rounded overflow-hidden">
                <div className="h-full bg-amber transition-all" style={{ width: `${pct}%` }} />
              </div>
              <div className="label-tiny">{done}/{names.length} — cloning {current ?? "…"}</div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2 py-1">
          <div className="text-[13px]">Cloned {names.length - failed.length}/{names.length} voices into OmniVoice.</div>
          {failed.length > 0 && (
            <p className="label-tiny text-err leading-relaxed">
              Failed: {failed.join(", ")}. Re-run from the voice picker once OmniVoice is healthy.
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}

function ShutdownDialog({ onClose }: { onClose: () => void }) {
  const [shutting, setShutting] = useState(false);

  async function go() {
    setShutting(true);
    try { await api.shutdown(); } catch { /* the server is going down — the request may not finish */ }
  }

  return (
    <Modal
      open
      onClose={shutting ? () => {} : onClose}
      title="Shut down MACU Studio"
      width={440}
      footer={shutting ? undefined : (
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-amber" onClick={go}>Shut down</button>
        </>
      )}
    >
      {!shutting ? (
        <p className="label-tiny leading-relaxed">
          This frees the GPU — it stops the ComfyUI, OmniVoice, and Ollama containers —
          and then stops the Studio server. To use Studio again you'll need to start it
          from a terminal (<span className="font-mono">./deploy/start-studio.sh</span>, or
          the systemd service).
        </p>
      ) : (
        <div className="flex flex-col gap-2 py-1">
          <div className="text-amber text-[13px]">MACU Studio is freeing the GPU and shutting down…</div>
          <p className="label-tiny leading-relaxed">
            You can close this browser tab now. Start Studio again from a terminal when you
            want to come back.
          </p>
        </div>
      )}
    </Modal>
  );
}

function NewShowDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
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
      pushToast(`show created: ${effId}`, "ok");
      onCreated(effId);
    } catch (e) {
      pushToast(`create show failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setBusy(false); }
  }

  return (
    <Modal
      open onClose={onClose} title="New show" width={440}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-amber" disabled={busy || !effId} onClick={create}>Create</button>
      </>}
    >
      <div className="flex flex-col gap-3">
        <Field label="Display name" value={name} onChange={setName} placeholder="My New Show" />
        <Field label="Show id (folder-safe)" value={effId}
               onChange={(v) => { setIdTouched(true); setId(v); }} placeholder="my-new-show" />
        <p className="label-tiny leading-relaxed">
          Episodes will live in a new folder. Voice/render defaults are copied from the
          current default show — edit them under Settings → Show metadata.
        </p>
      </div>
    </Modal>
  );
}

function NewEpisodeDialog({ show, onClose, onCreated }: { show: string; onClose: () => void; onCreated: (slug: string) => void }) {
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const pushToast = useStore((s) => s.pushToast);

  async function create() {
    setBusy(true);
    try {
      const r = await showsApi.createEpisode(show, slug, title);
      pushToast(`episode created: ${r.slug}`, "ok");
      onCreated(r.slug);
    } catch (e) {
      pushToast(`create episode failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setBusy(false); }
  }

  return (
    <Modal
      open onClose={onClose} title={`New episode in ${show}`} width={440}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-amber" disabled={busy || !slug} onClick={create}>Create</button>
      </>}
    >
      <div className="flex flex-col gap-3">
        <Field label="Slug (unique, folder-safe)" value={slug} onChange={setSlug} placeholder="ep-021" />
        <Field label="Title" value={title} onChange={setTitle} placeholder="The One About Lasers" />
        <p className="label-tiny leading-relaxed">
          Scaffolds a manifest + script seeded from this show's defaults. Then write the
          script and click Generate manifest.
        </p>
      </div>
    </Modal>
  );
}

function ExportDialog({ show, slug, onClose }: { show: string; slug: string; onClose: () => void }) {
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
    <Modal open onClose={onClose} title="Export project" width={420}>
      <div className="flex flex-col gap-2">
        <p className="label-tiny leading-relaxed">
          Bundles text files (script, manifest, youtube) + the title-card templates and
          OmniVoice reference clips the show uses into a .zip. Re-import it elsewhere; the
          import offers to re-clone the voices. Generated media is not included.
        </p>
        <button className="btn btn-amber justify-center" disabled={!slug} onClick={() => dl(exportUrl.episode(slug))}>
          Export this episode ({slug || "—"})
        </button>
        <button className="btn justify-center" onClick={() => dl(exportUrl.show(show))}>
          Export whole show ({show})
        </button>
        <button className="btn justify-center" onClick={() => dl(exportUrl.voicesAll())}>
          Export all voices
        </button>
        <p className="label-tiny leading-relaxed opacity-70">
          (A single voice can be exported from the Audio page's voice picker.)
        </p>
      </div>
    </Modal>
  );
}
