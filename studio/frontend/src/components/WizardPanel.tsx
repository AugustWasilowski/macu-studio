import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "../route";
import { useStore } from "../store";
import { useT } from "../i18n";
import { api } from "../api";
import { showsApi } from "../api/shows";
import { servicesApi } from "../api/diagnostics";
import { WIZARD_STEPS, type WizardService } from "../wizard/wizard";
import { useWizardGates } from "../wizard/useWizardGates";
import { STARTER_SLUG, STARTER_TITLE, STARTER_SCRIPT, STARTER_SHOW, STARTER_SHOW_NAME } from "../wizard/starterScript";

interface Props {
  routedSlug: string;
  go: (r: Partial<Route>) => void;
}

export function WizardPanel({ routedSlug, go }: Props) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const wizard = useStore((s) => s.wizard);
  const activeShow = useStore((s) => s.activeShow);
  const setStep = useStore((s) => s.setWizardStep);
  const skipStep = useStore((s) => s.skipWizardStep);
  const finish = useStore((s) => s.finishWizard);
  const pause = useStore((s) => s.pauseWizard);
  const setCollapsed = useStore((s) => s.setWizardCollapsed);
  // Hide behind any open right-hand drawer so the panel never overlaps them.
  const drawerBusy = useStore((s) => s.drawerOpen || s.logOpen || s.terminalOpen);

  const active = wizard?.status === "active";
  const step = active ? WIZARD_STEPS[wizard!.step] : undefined;
  const slug = wizard?.slug ?? "";

  // Drive the screen to the step's page so the user is looking at what the copy describes.
  useEffect(() => {
    if (active && step?.stage && slug) go({ page: "stage", slug, stage: step.stage });
  }, [wizard?.step, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const gate = useWizardGates(slug, step?.gate);
  const services = useQuery({
    queryKey: ["services", activeShow],
    queryFn: () => servicesApi.get(activeShow),
    enabled: active && !!step?.requiresService,
    staleTime: 30_000,
  });
  const serviceDown = (s?: WizardService) =>
    !!s && services.data != null && services.data[s] === false;
  const down = serviceDown(step?.requiresService);

  const setActiveShow = useStore((s) => s.setActiveShow);
  const createMut = useMutation({
    mutationFn: async () => {
      // The walkthrough always teaches inside the neutral starter show — never in
      // a real (possibly imported) show that happens to be active. Episode slugs
      // are globally unique, so if a previous run already created the starter
      // (in ANY show), adopt it where it lives instead of erroring; don't clobber
      // an edited script on resume/re-run.
      const { shows } = await showsApi.list();
      let owner: string | null = null;
      for (const s of shows) {
        const { episodes } = await api.episodes(s.id);
        if (episodes.some((e) => e.slug === STARTER_SLUG)) { owner = s.id; break; }
      }
      if (!owner) {
        if (!shows.some((s) => s.id === STARTER_SHOW)) {
          await showsApi.create(STARTER_SHOW, STARTER_SHOW_NAME);
        }
        await showsApi.createEpisode(STARTER_SHOW, STARTER_SLUG, STARTER_TITLE);
        await api.putScript(STARTER_SLUG, STARTER_SCRIPT);
        owner = STARTER_SHOW;
      }
      setActiveShow(owner);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["episodes"] });
      qc.invalidateQueries({ queryKey: ["shows"] });
    },
    onError: (e: Error) => push(t("wizard.createFailed", { msg: e.message }), "err"),
  });

  if (!active || !step) return null;

  const idx = wizard!.step;
  const last = idx === WIZARD_STEPS.length - 1;
  const canAdvance = !step.gate || gate.done;

  function advance() {
    if (last) finish();
    else setStep(idx + 1);
  }
  function doSkip() {
    skipStep(step!.id);
    advance();
  }

  // Collapsed chip (or forced-collapsed while a drawer is open).
  if (wizard!.collapsed || drawerBusy) {
    return (
      <button
        className="fixed bottom-3 right-3 z-[1500] panel px-3 py-1.5 flex items-center gap-2 hover:brightness-125"
        onClick={() => setCollapsed(false)}
        title={t("wizard.expand")}
      >
        <span className="led-dot pulse" style={{ "--led-c": "#33ddff" } as React.CSSProperties} />
        <span className="text-[11px] font-semibold tracking-wider uppercase text-cyan">
          {t("wizard.chip", { n: idx + 1, total: WIZARD_STEPS.length })}
        </span>
      </button>
    );
  }

  const onWizardEpisode = !routedSlug || routedSlug === slug;

  return (
    <div className="fixed bottom-3 right-3 z-[1500] panel p-3 flex flex-col gap-2 w-[320px]" style={{ borderColor: "var(--cyan)" }}>
      <div className="flex items-center justify-between">
        <div className="panel-title text-cyan">{t("wizard.panelTitle")}</div>
        <div className="flex items-center gap-2">
          <span className="label-tiny">{idx + 1}/{WIZARD_STEPS.length}</span>
          <button className="label-tiny hover:text-amber" onClick={() => setCollapsed(true)} title={t("wizard.collapse")}>▾</button>
          <button className="label-tiny hover:text-amber" onClick={pause} title={t("wizard.pause")}>✕</button>
        </div>
      </div>

      <div className="text-[13px] font-semibold text-txt">{t(step.titleKey)}</div>
      <p className="text-[12px] leading-relaxed text-txt-dim">{t(step.bodyKey)}</p>

      {step.goalKey && (
        <div className="flex items-center gap-2 rounded-[3px] px-2 py-1.5" style={{ background: "rgba(51,221,255,0.07)" }}>
          <span
            className="flex-none rounded-full"
            style={{
              width: 9, height: 9,
              background: gate.done ? "var(--green)" : "transparent",
              border: gate.done ? "none" : "1.5px solid var(--txt-faint)",
              boxShadow: gate.done ? "0 0 5px var(--green)" : "none",
            }}
          />
          <span className="text-[12px] text-txt-dim flex-1">{t(step.goalKey)}</span>
          {gate.detail && <span className="seg-readout text-[10px]">{gate.detail}</span>}
        </div>
      )}

      {down && (
        <p className="text-[11px] leading-relaxed text-amber rounded-[3px] px-2 py-1.5" style={{ background: "rgba(245,166,35,0.08)", borderLeft: "2px solid var(--amber)" }}>
          {t("wizard.serviceDown")}
        </p>
      )}

      {!onWizardEpisode && (
        <button className="text-[11px] text-amber text-left hover:underline" onClick={() => go({ page: "stage", slug, stage: step.stage ?? "script" })}>
          {t("wizard.jumpBack", { slug })}
        </button>
      )}

      <div className="flex items-center justify-between pt-1">
        {idx > 0 ? (
          <button className="btn" onClick={() => setStep(idx - 1)}>{t("common.back")}</button>
        ) : <span />}
        <div className="flex gap-2">
          {idx > 0 && !last && (step.optional || down || !canAdvance) && (
            <button className="btn" onClick={doSkip}>{t("wizard.skip")}</button>
          )}
          {step.action === "createEpisode" && !gate.done ? (
            <button className="btn btn-amber" disabled={createMut.isPending} onClick={() => createMut.mutate()}>
              {createMut.isPending ? t("wizard.creating") : t("wizard.createEpisode")}
            </button>
          ) : last ? (
            <button className="btn btn-amber" onClick={finish}>{t("wizard.finish")}</button>
          ) : (
            <button className="btn btn-amber" disabled={!canAdvance} onClick={advance}>{t("wizard.next")}</button>
          )}
        </div>
      </div>
    </div>
  );
}
