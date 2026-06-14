import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { charactersApi } from "../api/characters";
import type { Character, CharSummary, Take, UsageRow, UseResult } from "../api/characters";
import { enginesApi } from "../api/engines";
import { higgsfieldApi } from "../api/higgsfield";
import type { HfGeneration } from "../api/higgsfield";
import { showsApi } from "../api/shows";
import { Field } from "../components/Field";
import { Modal } from "../components/Modal";
import { useStore } from "../store";
import { useT } from "../i18n";

// Show-level character library: roster on the left, character detail (prompts,
// reference-still takes, generation, episode sync) on the right. Stills crafted
// here feed Higgsfield image-to-video + lipsync shots via "use in episode".
export function Characters() {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const show = useStore((s) => s.activeShow);

  const roster = useQuery({ queryKey: ["characters", show], queryFn: () => charactersApi.roster(show) });
  const [selKey, setSelKey] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => { setSelKey(null); }, [show]);
  const list = (roster.data?.characters ?? []).filter(
    (c) => !filter || c.key.includes(filter.toLowerCase()) || (c.name ?? "").toLowerCase().includes(filter.toLowerCase()),
  );
  useEffect(() => {
    if (!selKey && list.length) setSelKey(list[0].key);
  }, [list, selKey]);

  const refetchRoster = () => qc.invalidateQueries({ queryKey: ["characters", show] });

  return (
    <div className="grid grid-cols-[280px_minmax(0,1fr)] gap-3 h-full min-h-0">
      {/* ---- roster ---- */}
      <section className="panel flex flex-col min-h-0">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">{t("characters.rosterTitle")}</div>
          <button className="btn btn-cyan text-[11px]" onClick={() => setNewOpen(true)}>+ {t("characters.new")}</button>
        </header>
        <div className="p-2 border-b hairline-soft">
          <input className="input w-full py-1 text-[12px]" placeholder={t("characters.searchPh")}
                 value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <div className="overflow-y-auto flex-1">
          {list.map((c) => (
            <RosterRow key={c.key} show={show} c={c} active={selKey === c.key} onClick={() => setSelKey(c.key)} />
          ))}
          {list.length === 0 && !roster.isLoading && (
            <div className="p-3 text-txt-faint text-[12px]">{t("characters.empty")}</div>
          )}
        </div>
        <footer className="p-2 border-t hairline-soft">
          <button className="btn w-full justify-center text-[11px]" onClick={() => setImportOpen(true)}>
            {t("characters.importFromEpisode")}
          </button>
        </footer>
      </section>

      {/* ---- detail ---- */}
      {selKey ? (
        <CharacterDetail show={show} charKey={selKey} onDeleted={() => { setSelKey(null); refetchRoster(); }}
                         onChanged={refetchRoster} />
      ) : (
        <section className="panel grid place-items-center text-txt-faint">{t("characters.noneSelected")}</section>
      )}

      <NewCharacterDialog show={show} open={newOpen} onClose={() => setNewOpen(false)}
        onCreated={(key) => { refetchRoster(); setSelKey(key); }} />
      <ImportEpisodeDialog show={show} open={importOpen} onClose={() => setImportOpen(false)}
        onDone={(r) => { refetchRoster(); push(t("characters.imported", { n: r.created.length, skipped: r.skipped.length }), "ok"); }} />
    </div>
  );
}

function RosterRow({ show, c, active, onClick }: { show: string; c: CharSummary; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={"w-full flex items-center gap-2 px-2 py-1.5 border-b border-[var(--line-soft)] text-left hover:bg-bg-3 " + (active ? "bg-bg-3" : "")}>
      {c.default_take ? (
        <img src={charactersApi.takeUrl(show, c.key, c.default_take, true)} alt=""
             className="rounded bg-black flex-none" style={{ width: 36, height: 36, objectFit: "cover" }} />
      ) : (
        <span className="rounded bg-bg-3 grid place-items-center flex-none text-txt-faint" style={{ width: 36, height: 36 }}>?</span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-[12px] truncate">{c.name}</span>
        <span className="block label-tiny font-mono truncate">{c.key}</span>
      </span>
      <span className="label-tiny flex-none">{c.take_count}</span>
    </button>
  );
}

function CharacterDetail({ show, charKey, onDeleted, onChanged }: {
  show: string; charKey: string; onDeleted: () => void; onChanged: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const c = useQuery({
    queryKey: ["character", show, charKey],
    queryFn: () => charactersApi.get(show, charKey),
    refetchInterval: (q) => (q.state.data?.job && ["queued", "generating", "downloading"].includes(q.state.data.job.state) ? 2000 : false),
  });
  const refetch = () => { qc.invalidateQueries({ queryKey: ["character", show, charKey] }); onChanged(); };

  // editable fields (save-on-blur)
  const [draft, setDraft] = useState<{ name: string; core: string; still_prompt: string; voice_hint: string } | null>(null);
  useEffect(() => { setDraft(null); }, [charKey]);
  const d = draft ?? {
    name: c.data?.name ?? "", core: c.data?.core ?? "",
    still_prompt: c.data?.still_prompt ?? "", voice_hint: c.data?.voice_hint ?? "",
  };
  const saveField = async (field: keyof typeof d, value: string) => {
    if (!c.data || c.data[field] === value) return;
    try {
      await charactersApi.update(show, charKey, { [field]: value });
      refetch();
    } catch (e) { push(String(e), "err"); }
  };

  const [zoomTake, setZoomTake] = useState<Take | null>(null);
  const [useOpen, setUseOpen] = useState<string | null>(null); // take id
  const [importOpen, setImportOpen] = useState(false);

  if (c.isLoading) return <section className="panel grid place-items-center text-txt-dim">{t("common.loading")}</section>;
  if (c.isError || !c.data) return <section className="panel grid place-items-center text-red">{String(c.error)}</section>;
  const ch = c.data;
  const job = ch.job;
  const busy = !!job && ["queued", "generating", "downloading"].includes(job.state);

  return (
    <section className="panel flex flex-col min-h-0 overflow-y-auto">
      <header className="flex items-center gap-3 px-3 py-2 border-b hairline">
        <div className="panel-title flex-1">{ch.name} <span className="text-txt-faint font-mono normal-case text-[11px]">/ {ch.key}</span></div>
        <button className="btn text-[11px]" onClick={async () => {
          if (!confirm(t("characters.deleteConfirm", { key: ch.key }))) return;
          await charactersApi.remove(show, charKey);
          push(t("characters.deleted", { key: ch.key }), "ok");
          onDeleted();
        }}>{t("common.delete")}</button>
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)_320px] gap-3 p-3">
        {/* left column: prompts */}
        <div className="flex flex-col gap-2">
          <Field label={t("characters.fieldName")} value={d.name}
                 onChange={(v) => setDraft({ ...d, name: v })} onBlur={() => saveField("name", d.name)} />
          <Field label={t("characters.fieldCore")} value={d.core} rows={3}
                 placeholder={t("characters.fieldCorePh")}
                 onChange={(v) => setDraft({ ...d, core: v })} onBlur={() => saveField("core", d.core)} />
          <Field label={t("characters.fieldStillPrompt")} value={d.still_prompt} rows={4}
                 placeholder={t("characters.fieldStillPromptPh")}
                 onChange={(v) => setDraft({ ...d, still_prompt: v })} onBlur={() => saveField("still_prompt", d.still_prompt)} />
          <FinalPromptChip show={show} stillPrompt={d.still_prompt} />
          <Field label={t("characters.fieldVoiceHint")} value={d.voice_hint}
                 onChange={(v) => setDraft({ ...d, voice_hint: v })} onBlur={() => saveField("voice_hint", d.voice_hint)} />
          <UsagePanel show={show} charKey={charKey} />
        </div>

        {/* right column: generate */}
        <GeneratePanel show={show} charKey={charKey} stillPrompt={ch.still_prompt} busy={busy} job={job} onStarted={refetch} />
      </div>

      {/* takes grid */}
      <div className="px-3 pb-3">
        <div className="flex items-center pb-1">
          <div className="label-tiny flex-1">{t("characters.takesTitle", { n: ch.takes.length })}</div>
          <ImportFromHfButton onOpen={() => setImportOpen(true)} />
          <TrainSoulButton show={show} charKey={charKey} name={ch.name} takes={ch.takes} />
        </div>
        <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}>
          {ch.takes.map((take) => (
            <TakeCard key={take.id} show={show} charKey={charKey} take={take}
                      isDefault={ch.default_take === take.id}
                      onDefault={async () => { await charactersApi.setDefault(show, charKey, take.id); refetch(); }}
                      onDelete={async () => { await charactersApi.deleteTake(show, charKey, take.id); refetch(); }}
                      onZoom={() => setZoomTake(take)}
                      onUse={() => setUseOpen(take.id)}
                      onElement={async () => {
                        try {
                          const el = await charactersApi.takeToElement(show, charKey, take.id, ch.name);
                          push(t("characters.elementCreated", { name: el.name || el.id }), "ok");
                          qc.invalidateQueries({ queryKey: ["hf-elements"] });
                        } catch (e) { push(String(e), "err"); }
                      }} />
          ))}
          {ch.takes.length === 0 && <div className="text-txt-faint text-[12px] py-4">{t("characters.noTakes")}</div>}
        </div>
      </div>

      {zoomTake && (
        <Modal open onClose={() => setZoomTake(null)} title={`${ch.key} / ${zoomTake.id}`} width={760}>
          <img src={charactersApi.takeUrl(show, charKey, zoomTake.id)} alt={zoomTake.id}
               className="w-full bg-black rounded" style={{ aspectRatio: "1/1", objectFit: "contain" }} />
          <div className="label-tiny pt-2 font-mono">
            {zoomTake.engine}{zoomTake.model ? ` · ${zoomTake.model}` : ""}{zoomTake.seed != null ? ` · seed ${zoomTake.seed}` : ""}
          </div>
          <HfMetaChips take={zoomTake} full />
          {zoomTake.prompt && <p className="text-[12px] text-txt-dim pt-1 whitespace-pre-wrap">{zoomTake.prompt}</p>}
        </Modal>
      )}
      {useOpen && (
        <UseInEpisodeDialog show={show} charKey={charKey} takeId={useOpen}
                            onClose={() => setUseOpen(null)} />
      )}
      {importOpen && (
        <ImportFromHfModal show={show} charKey={charKey} onClose={() => setImportOpen(false)}
                           onImported={() => { refetch(); }} />
      )}
    </section>
  );
}

function TakeCard({ show, charKey, take, isDefault, onDefault, onDelete, onZoom, onUse, onElement }: {
  show: string; charKey: string; take: Take; isDefault: boolean;
  onDefault: () => void; onDelete: () => void; onZoom: () => void; onUse: () => void; onElement: () => void;
}) {
  const t = useT();
  const isHf = take.engine === "higgsfield";
  return (
    <div className="group relative rounded overflow-hidden hairline-soft"
         style={isDefault ? { outline: "2px solid var(--amber)", boxShadow: "var(--glow-amber)" } : {}}>
      <img src={charactersApi.takeUrl(show, charKey, take.id, true)} alt={take.id}
           className="w-full bg-black cursor-zoom-in" style={{ aspectRatio: "1/1", objectFit: "cover" }}
           onClick={onZoom} />
      <div className="flex items-center justify-between px-1.5 py-1 text-[10px] bg-bg-2">
        <span className="font-mono truncate">{take.id}{take.seed != null ? ` · ${take.seed}` : ""}</span>
        <span className="label-tiny">{take.engine === "comfy_zimage" ? "local" : take.engine}</span>
      </div>
      <HfMetaChips take={take} />
      <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!isDefault && (
          <button className="btn p-1 text-[10px]" title={t("characters.setDefault")} onClick={onDefault}>★</button>
        )}
        {isHf && (
          <button className="btn p-1 text-[10px]" title={t("characters.takeToElement")} onClick={onElement}>⧉</button>
        )}
        <button className="btn p-1 text-[10px]" title={t("characters.useInEpisode")} onClick={onUse}>⤵</button>
        <button className="btn p-1 text-[10px]" title={t("common.delete")} onClick={onDelete}>🗑</button>
      </div>
      {isDefault && <span className="absolute top-1 left-1 text-amber text-[11px]" title={t("characters.defaultTake")}>★</span>}
    </div>
  );
}

// Train a Higgsfield Soul from this character's takes (SSA-129). The take library is
// already a same-identity reference set; HF wants 5–20. Async — the new Soul shows up
// in the identity picker once it's done training. Hidden unless HF is connected.
function TrainSoulButton({ show, charKey, name, takes }: {
  show: string; charKey: string; name: string; takes: Take[];
}) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const account = useQuery({ queryKey: ["hf-account"], queryFn: higgsfieldApi.account, staleTime: 60_000, retry: false });
  const [busy, setBusy] = useState(false);
  if (!account.data?.connected) return null;
  const enough = takes.length >= 5;
  const train = async () => {
    const ids = takes.slice(0, 20).map((tk) => tk.id);
    if (!confirm(t("characters.trainSoulConfirm", { n: ids.length, name }))) return;
    setBusy(true);
    try {
      await charactersApi.trainSoul(show, charKey, { take_ids: ids, name });
      push(t("characters.trainSoulStarted", { name }), "ok");
      qc.invalidateQueries({ queryKey: ["hf-souls"] });
    } catch (e) { push(String(e), "err"); } finally { setBusy(false); }
  };
  return (
    <button className="btn text-[11px]" disabled={!enough || busy} onClick={train}
            title={enough ? t("characters.trainSoulTitle") : t("characters.trainSoulNeed")}>
      {t("characters.trainSoul")}
    </button>
  );
}

// "Import from Higgsfield" entry — hidden unless HF is connected.
function ImportFromHfButton({ onOpen }: { onOpen: () => void }) {
  const t = useT();
  const account = useQuery({ queryKey: ["hf-account"], queryFn: higgsfieldApi.account, staleTime: 60_000, retry: false });
  if (!account.data?.connected) return null;
  return <button className="btn text-[11px]" onClick={onOpen} title={t("characters.importHfTitle")}>{t("characters.importHf")}</button>;
}

// Browse the HF account's image generations (web- or API-made) and pull one in as a
// take — the $0 loop (generate free in the web app, harvest here). SSA-132.
function ImportFromHfModal({ show, charKey, onClose, onImported }: {
  show: string; charKey: string; onClose: () => void; onImported: () => void;
}) {
  const t = useT();
  const push = useStore((s) => s.pushToast);
  const gens = useQuery({ queryKey: ["hf-generations", "image"], queryFn: () => higgsfieldApi.generations("image"), retry: false });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [done, setDone] = useState<Set<string>>(new Set());

  const importOne = async (g: HfGeneration) => {
    setBusyId(g.id);
    try {
      await charactersApi.importGeneration(show, charKey, g.id);
      setDone((s) => new Set(s).add(g.id));
      push(t("characters.importHfDone"), "ok");
      onImported();
    } catch (e) { push(String(e), "err"); } finally { setBusyId(null); }
  };

  const items = gens.data?.items ?? [];
  return (
    <Modal open onClose={onClose} title={t("characters.importHfTitle")} width={820}>
      {gens.isLoading && <div className="text-txt-dim p-4">{t("common.loading")}</div>}
      {gens.isError && <div className="text-red p-4 text-[12px]">{String(gens.error)}</div>}
      {!gens.isLoading && !gens.isError && items.length === 0 && (
        <div className="text-txt-faint p-4 text-[12px]">{t("characters.importHfEmpty")}</div>
      )}
      <div className="grid gap-2 max-h-[460px] overflow-y-auto" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
        {items.map((g) => {
          const thumb = g.results?.minUrl || g.results?.thumbnailUrl || g.results?.rawUrl;
          const imported = done.has(g.id);
          return (
            <button key={g.id} className="group relative rounded overflow-hidden hairline-soft text-left disabled:opacity-60"
                    disabled={busyId === g.id || imported} onClick={() => importOne(g)} title={g.params?.prompt || g.id}>
              {thumb
                ? <img src={thumb} alt="" className="w-full bg-black" style={{ aspectRatio: "1/1", objectFit: "cover" }} />
                : <div className="w-full bg-bg-3 grid place-items-center text-txt-faint" style={{ aspectRatio: "1/1" }}>?</div>}
              <div className="flex items-center justify-between px-1.5 py-1 text-[10px] bg-bg-2">
                <span className="font-mono truncate">{g.model || g.type}</span>
                {imported ? <span className="text-amber">✓</span>
                          : busyId === g.id ? <span className="label-tiny">…</span>
                          : <span className="label-tiny opacity-0 group-hover:opacity-100">⤵</span>}
              </div>
            </button>
          );
        })}
      </div>
      <p className="label-tiny pt-2 leading-relaxed">{t("characters.importHfHelp")}</p>
    </Modal>
  );
}

// Generation-provenance chips for an HF take (model_used / resolution / Soul|Element
// ref). `full` adds job id + a raw-image link in the zoom modal. No-op for non-HF takes.
function HfMetaChips({ take, full = false }: { take: Take; full?: boolean }) {
  const t = useT();
  const hf = take.hf;
  if (!hf) return null;
  const chip = (txt: string, title?: string) => (
    <span key={txt} className="label-tiny px-1 rounded bg-bg-3 truncate" title={title || txt}>{txt}</span>
  );
  const chips = [];
  if (hf.model_used) chips.push(chip(hf.model_used));
  if (hf.resolution) chips.push(chip(hf.resolution));
  else if (hf.width && hf.height) chips.push(chip(`${hf.width}×${hf.height}`));
  if (hf.soul_id) chips.push(chip(t("characters.soulBadge"), `soul ${hf.soul_id}`));
  if (hf.element_id) chips.push(chip(t("characters.elementBadge"), `element ${hf.element_id}`));
  return (
    <div className={"flex flex-wrap gap-1 " + (full ? "pt-2" : "px-1.5 pb-1")}>
      {chips}
      {full && hf.job_id && chip(`job ${hf.job_id.slice(0, 8)}`, hf.job_id)}
      {full && hf.raw_url && (
        <a className="label-tiny px-1 rounded bg-bg-3 underline" href={hf.raw_url} target="_blank" rel="noopener noreferrer">
          {t("characters.rawImage")}
        </a>
      )}
    </div>
  );
}

// Read-only preview of the prompt actually sent to the engine: the still prompt
// plus the show's appended style suffix (SSA-129 — surfaces the silent append).
function FinalPromptChip({ show, stillPrompt }: { show: string; stillPrompt: string }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const cfg = useQuery({ queryKey: ["show-config", show], queryFn: () => showsApi.config(show), staleTime: 300_000 });
  const ed = (cfg.data?.episode_defaults ?? {}) as { style?: { suffix?: string } };
  const suffix = (ed.style?.suffix ?? "").trim();
  if (!stillPrompt.trim() && !suffix) return null;
  const base = stillPrompt.trim();
  const final = suffix && !base.endsWith(suffix) ? `${base}${base ? ", " : ""}${suffix.replace(/^,\s*/, "")}` : base;
  return (
    <div className="rounded hairline-soft text-[11px]">
      <button className="w-full flex items-center gap-1 px-2 py-1 text-left label-tiny hover:text-amber"
              onClick={() => setOpen((o) => !o)}>
        <span>{open ? "▾" : "▸"}</span>{t("characters.finalPrompt")}
        {suffix && <span className="ml-auto label-tiny">{t("characters.styleAppended")}</span>}
      </button>
      {open && (
        <p className="px-2 pb-2 text-txt-dim whitespace-pre-wrap font-mono leading-relaxed">{final || t("characters.finalPromptEmpty")}</p>
      )}
    </div>
  );
}

// Pick a trained Soul or a reusable Element to lock character identity across HF
// generations (SSA-129). Souls = soul_2 + soul_id; Elements = <<<id>>> prompt inject.
function HfIdentityPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const t = useT();
  const account = useQuery({ queryKey: ["hf-account"], queryFn: higgsfieldApi.account, staleTime: 60_000, retry: false });
  const connected = !!account.data?.connected;
  const souls = useQuery({ queryKey: ["hf-souls"], queryFn: () => higgsfieldApi.souls(), enabled: connected, retry: false });
  const elements = useQuery({ queryKey: ["hf-elements"], queryFn: () => higgsfieldApi.elements(), enabled: connected, retry: false });

  if (!connected) {
    return <p className="label-tiny leading-relaxed">{t("characters.hfNotConnected")}</p>;
  }
  const soulItems = (souls.data?.items ?? []).filter((s) => !s.status || s.status === "ready");
  const elItems = elements.data?.items ?? [];
  return (
    <label className="flex flex-col gap-1 text-[12px]">
      <span className="label-tiny">{t("characters.identityRef")}</span>
      <select className="input text-[12px] py-0.5" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("characters.identityNone")}</option>
        {elItems.length > 0 && (
          <optgroup label={t("characters.elementsGroup")}>
            {elItems.map((el) => <option key={el.id} value={`element:${el.id}`}>{el.name || el.id}</option>)}
          </optgroup>
        )}
        {soulItems.length > 0 && (
          <optgroup label={t("characters.soulsGroup")}>
            {soulItems.map((s) => <option key={s.id} value={`soul:${s.id}`}>{s.name || s.id}</option>)}
          </optgroup>
        )}
      </select>
      {soulItems.length === 0 && elItems.length === 0 && (
        <span className="label-tiny leading-relaxed">{t("characters.identityEmpty")}</span>
      )}
    </label>
  );
}

function GeneratePanel({ show, charKey, stillPrompt, busy, job, onStarted }: {
  show: string; charKey: string; stillPrompt: string; busy: boolean;
  job: Character["job"]; onStarted: () => void;
}) {
  const t = useT();
  const push = useStore((s) => s.pushToast);
  const engines = useQuery({ queryKey: ["engines"], queryFn: enginesApi.get, staleTime: 60_000 });
  const stillEngines = engines.data?.capabilities.find((c) => c.id === "stills")?.engines ?? [];
  const routed = engines.data?.routing.stills ?? "comfy_zimage";

  const [engine, setEngine] = useState("");
  const [prompt, setPrompt] = useState("");
  const [seed, setSeed] = useState("");
  const [count, setCount] = useState(1);
  // Consistent-identity ref for the HF engine: "" | "soul:<id>" | "element:<id>".
  const [identity, setIdentity] = useState("");
  useEffect(() => { setPrompt(""); setSeed(""); setCount(1); setIdentity(""); }, [charKey]);

  const effEngine = engine || routed;
  const isHf = effEngine === "higgsfield";

  const start = async () => {
    try {
      const [kind, id] = identity ? identity.split(":") : [];
      const r = await charactersApi.generate(show, charKey, {
        engine: engine || undefined,
        prompt: prompt.trim() || undefined,
        seed: seed.trim() ? parseInt(seed, 10) : undefined,
        count,
        ...(isHf && kind === "soul" ? { soul_id: id } : {}),
        ...(isHf && kind === "element" ? { element_id: id } : {}),
      });
      push(t("characters.genQueued", { n: r.count, engine: r.engine }), "run");
      onStarted();
    } catch (e) {
      push(String(e), "err");
    }
  };

  return (
    <div className="flex flex-col gap-2 p-2 rounded hairline-soft self-start">
      <div className="label-tiny">{t("characters.genTitle")}</div>
      <label className="flex flex-col gap-1 text-[12px]">
        <span className="label-tiny">{t("characters.genEngine")}</span>
        <select className="input text-[12px] py-0.5" value={engine} onChange={(e) => setEngine(e.target.value)}>
          <option value="">{t("characters.genEngineDefault", { engine: t(`engines.name.${routed}`) })}</option>
          {stillEngines.map((e) => (
            <option key={e.id} value={e.id} disabled={!e.available}>
              {t(`engines.name.${e.id}`)}{!e.available && e.reason ? ` — ${e.reason}` : ""}
              {e.id === "higgsfield" ? ` (${t("characters.genCredits")})` : ""}
            </option>
          ))}
        </select>
      </label>
      {isHf && <HfIdentityPicker value={identity} onChange={setIdentity} />}
      <Field label={t("characters.genPrompt")} value={prompt} rows={3}
             placeholder={stillPrompt || t("characters.genPromptPh")} onChange={setPrompt} />
      <div className="grid grid-cols-2 gap-2">
        <Field label={t("characters.genSeed")} value={seed} type="number" placeholder="random" onChange={setSeed} />
        <label className="flex flex-col gap-1 text-[12px]">
          <span className="label-tiny">{t("characters.genCount")}</span>
          <select className="input text-[12px] py-0.5" value={count} onChange={(e) => setCount(parseInt(e.target.value, 10))}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>
      <button className="btn btn-amber justify-center" disabled={busy} onClick={start}>
        {busy && job
          ? t("characters.genProgress", { done: job.progress.done, total: job.progress.total })
          : t("characters.genGo")}
      </button>
      {job?.state === "error" && <span className="label-tiny text-red">{job.error}</span>}
    </div>
  );
}

function UsagePanel({ show, charKey }: { show: string; charKey: string }) {
  const t = useT();
  const usage = useQuery({ queryKey: ["char-usage", show, charKey], queryFn: () => charactersApi.usage(show, charKey) });
  const rows = usage.data?.usage ?? [];
  if (!rows.length) return null;
  const COLOR: Record<UsageRow["state"], string> = {
    in_sync: "var(--green, #0c6)", stale: "var(--amber, #fa3)",
    diverged: "var(--cyan, #0cc)", no_still: "var(--line-soft)",
  };
  return (
    <div className="flex flex-col gap-1 pt-1">
      <div className="label-tiny">{t("characters.usageTitle")}</div>
      <div className="flex flex-wrap gap-1">
        {rows.map((r) => (
          <span key={r.slug} className="flex items-center gap-1 px-1.5 py-0.5 rounded hairline-soft text-[11px] font-mono"
                title={t(`characters.usage.${r.state}`)}>
            <span className="rounded-full" style={{ width: 7, height: 7, background: COLOR[r.state] }} />
            {r.slug}
          </span>
        ))}
      </div>
    </div>
  );
}

function NewCharacterDialog({ show, open, onClose, onCreated }: {
  show: string; open: boolean; onClose: () => void; onCreated: (key: string) => void;
}) {
  const t = useT();
  const push = useStore((s) => s.pushToast);
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [stillPrompt, setStillPrompt] = useState("");
  useEffect(() => { if (!open) { setKey(""); setName(""); setStillPrompt(""); } }, [open]);
  const submit = async () => {
    try {
      const c = await charactersApi.create(show, { key: key.trim(), name: name.trim() || undefined, still_prompt: stillPrompt.trim() || undefined });
      push(t("characters.created", { key: c.key }), "ok");
      onCreated(c.key);
      onClose();
    } catch (e) { push(String(e), "err"); }
  };
  return (
    <Modal open={open} onClose={onClose} title={t("characters.newTitle")} width={460}
      footer={<>
        <button className="btn" onClick={onClose}>{t("common.close")}</button>
        <button className="btn btn-cyan" disabled={!key.trim()} onClick={submit}>{t("characters.createBtn")}</button>
      </>}>
      <div className="flex flex-col gap-2">
        <Field label={t("characters.fieldKey")} value={key} onChange={(v) => setKey(v.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
               placeholder="ron" monospace />
        <Field label={t("characters.fieldName")} value={name} onChange={setName} placeholder="Ron Stone" />
        <Field label={t("characters.fieldStillPrompt")} value={stillPrompt} rows={3} onChange={setStillPrompt}
               placeholder={t("characters.fieldStillPromptPh")} />
      </div>
    </Modal>
  );
}

function ImportEpisodeDialog({ show, open, onClose, onDone }: {
  show: string; open: boolean; onClose: () => void;
  onDone: (r: { created: string[]; skipped: string[] }) => void;
}) {
  const t = useT();
  const push = useStore((s) => s.pushToast);
  const eps = useQuery({ queryKey: ["episodes", show], queryFn: () => api.episodes(show), enabled: open });
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) { setSlug(""); setBusy(false); } }, [open]);
  return (
    <Modal open={open} onClose={onClose} title={t("characters.importTitle")} width={420}
      footer={<>
        <button className="btn" onClick={onClose}>{t("common.close")}</button>
        <button className="btn btn-cyan" disabled={!slug || busy} onClick={async () => {
          setBusy(true);
          try { onDone(await charactersApi.importEpisode(show, slug)); onClose(); }
          catch (e) { push(String(e), "err"); }
          setBusy(false);
        }}>{t("characters.importBtn")}</button>
      </>}>
      <p className="label-tiny leading-relaxed pb-2">{t("characters.importHelp")}</p>
      <select className="input w-full text-[12px]" value={slug} onChange={(e) => setSlug(e.target.value)}>
        <option value="">—</option>
        {(eps.data?.episodes ?? []).map((e) => <option key={e.slug} value={e.slug}>{e.slug}</option>)}
      </select>
    </Modal>
  );
}

function UseInEpisodeDialog({ show, charKey, takeId, onClose }: {
  show: string; charKey: string; takeId: string; onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const eps = useQuery({ queryKey: ["episodes", show], queryFn: () => api.episodes(show) });
  const usage = useQuery({ queryKey: ["char-usage", show, charKey], queryFn: () => charactersApi.usage(show, charKey) });
  const [slug, setSlug] = useState("");
  const [confirmData, setConfirmData] = useState<UseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const usageOf = (s: string) => usage.data?.usage.find((u) => u.slug === s)?.state;

  const run = async (overwrite: boolean) => {
    setBusy(true);
    try {
      const r = await charactersApi.use(show, charKey, { slug, take: takeId, overwrite_still: overwrite });
      if (r.needs_confirm) {
        setConfirmData(r);
      } else {
        push(t("characters.usedIn", { key: charKey, slug }), "ok");
        qc.invalidateQueries({ queryKey: ["char-usage", show, charKey] });
        qc.invalidateQueries({ queryKey: ["shots", slug] });
        qc.invalidateQueries({ queryKey: ["manifest", slug] });
        onClose();
      }
    } catch (e) { push(String(e), "err"); }
    setBusy(false);
  };

  return (
    <Modal open onClose={onClose} title={t("characters.useTitle", { take: takeId })} width={460}
      footer={<>
        <button className="btn" onClick={onClose}>{t("common.close")}</button>
        {confirmData ? (
          <button className="btn btn-amber" disabled={busy} onClick={() => run(true)}>{t("characters.useOverwrite")}</button>
        ) : (
          <button className="btn btn-cyan" disabled={!slug || busy} onClick={() => run(false)}>{t("characters.useGo")}</button>
        )}
      </>}>
      <div className="flex flex-col gap-2">
        <p className="label-tiny leading-relaxed">{t("characters.useHelp")}</p>
        <select className="input w-full text-[12px]" value={slug}
                onChange={(e) => { setSlug(e.target.value); setConfirmData(null); }}>
          <option value="">—</option>
          {(eps.data?.episodes ?? []).map((e) => (
            <option key={e.slug} value={e.slug}>
              {e.slug}{usageOf(e.slug) ? ` (${t(`characters.usage.${usageOf(e.slug)}`)})` : ""}
            </option>
          ))}
        </select>
        {confirmData && (
          <div className="flex flex-col gap-1 p-2 rounded hairline-soft">
            <span className="text-[12px] text-amber">{t("characters.useConfirm")}</span>
            {confirmData.invalidates.length > 0 && (
              <span className="text-[12px] text-red">
                {t("characters.useInvalidates", { n: confirmData.invalidates.length, shots: confirmData.invalidates.join(", ") })}
              </span>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
