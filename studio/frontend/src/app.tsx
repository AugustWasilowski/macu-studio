import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "./api";
import { Topbar } from "./components/Topbar";
import { Settings } from "./components/Settings";
import { Tour, TOUR_DONE_KEY } from "./components/Tour";
import { Toasts } from "./components/Toasts";
import { Assembly } from "./stages/Assembly";
import { Audio } from "./stages/Audio";
import { Script } from "./stages/Script";
import { Video } from "./stages/Video";
import { Graphics } from "./stages/Graphics";
import { Publish } from "./stages/Publish";
import { Docs } from "./stages/Docs";
import { Characters } from "./stages/Characters";
import { Placeholder } from "./stages/Placeholder";
import { ManifestDrawer } from "./components/ManifestDrawer";
import { WizardPanel } from "./components/WizardPanel";
import { LogDrawer } from "./components/LogDrawer";
import { TerminalDrawer } from "./components/TerminalDrawer";
import { UpdateModal } from "./components/UpdateModal";
import { DiagnosticsModal } from "./components/DiagnosticsModal";
import { useRoute, Page } from "./route";
import { enterStage } from "./lib/motion";
import { useServerEvents } from "./hooks";
import { useStore } from "./store";
import { versionApi } from "./api/version";
import { STARTER_SLUG } from "./wizard/starterScript";
import { UIStage } from "./types";

// Auto-open the update modal at most once per day. We persist the last auto-prompt
// time so a page refresh doesn't re-pop the dialog every reload (manual "Check for
// updates" from the File menu is unaffected — it bypasses this gate).
const UPDATE_PROMPT_KEY = "macu-studio.updatePrompt.lastShown";
const UPDATE_PROMPT_INTERVAL_MS = 24 * 60 * 60 * 1000;

function updatePromptedRecently(): boolean {
  try {
    const ts = Number(localStorage.getItem(UPDATE_PROMPT_KEY));
    return Number.isFinite(ts) && ts > 0 && Date.now() - ts < UPDATE_PROMPT_INTERVAL_MS;
  } catch {
    return false;
  }
}

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={qc}>
      <Shell />
      <div className="crt-overlay" aria-hidden="true" />
      <Toasts />
    </QueryClientProvider>
  );
}

function Shell() {
  useServerEvents();   // toast everything the box does, MCP/API-driven included
  const [route, go] = useRoute();
  const activeSlug = useStore((s) => s.activeSlug);
  const setActiveSlug = useStore((s) => s.setActiveSlug);
  const activeShow = useStore((s) => s.activeShow);
  // ?settings=1 deep-links straight into the Settings modal (default tab is
  // Theme) and suppresses the first-run tour — used for sharing/screenshots.
  const [settingsOpen, setSettingsOpen] = useState(() => new URLSearchParams(location.search).has("settings"));
  const [tourOpen, setTourOpen] = useState(
    () => !localStorage.getItem(TOUR_DONE_KEY) && !new URLSearchParams(location.search).has("settings")
  );
  const startWizard = useStore((s) => s.startWizard);
  const wizardActive = useStore((s) => s.wizard?.status === "active");
  const episodes = useQuery({
    queryKey: ["episodes", activeShow],
    queryFn: () => api.episodes(activeShow),
    refetchInterval: 5000,        // keep the picker's git-sync dots fresh as files change
    refetchOnWindowFocus: true,
  });

  // Check for a newer build on launch and auto-open the update modal once — but never on top
  // of the first-run tutorial. Let the tour play out; the modal opens when it closes.
  const openUpdate = useStore((s) => s.openUpdate);
  const updateOpen = useStore((s) => s.updateOpen);
  const launchCheck = useQuery({
    queryKey: ["version", "launch"],
    queryFn: versionApi.check,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const updateAvailable = !!launchCheck.data?.update_available;
  const [autoPrompted, setAutoPrompted] = useState(false);
  useEffect(() => {
    if (autoPrompted || tourOpen || wizardActive || !updateAvailable || updateOpen) return;
    setAutoPrompted(true);
    if (updatePromptedRecently()) return;  // already auto-prompted within the last day
    try { localStorage.setItem(UPDATE_PROMPT_KEY, String(Date.now())); } catch { /* non-fatal */ }
    openUpdate();
  }, [autoPrompted, tourOpen, wizardActive, updateAvailable, updateOpen, openUpdate]);

  // Keep the store's activeSlug in sync with the routed slug on stage pages.
  useEffect(() => {
    if (route.page === "stage" && route.slug && route.slug !== activeSlug) {
      setActiveSlug(route.slug);
    }
  }, [route.page, route.slug, activeSlug, setActiveSlug]);

  // Default to a slug once we know what's available (stage pages only). Also
  // re-pick when the routed slug isn't part of the active show (e.g. right after
  // switching shows, which clears the slug).
  useEffect(() => {
    const eps = episodes.data?.episodes;
    if (route.page !== "stage" || !eps?.length) return;
    const inShow = route.slug && eps.some((e) => e.slug === route.slug);
    if (!inShow) {
      const pick = eps[eps.length - 1];
      go({ slug: pick.slug, stage: route.stage });
    }
  }, [episodes.data, route.page, route.slug, route.stage, go]);

  const eps = episodes.data?.episodes ?? [];
  // On top-level pages, the active episode comes from the store.
  const slug = route.page === "stage" ? route.slug : activeSlug ?? "";

  return (
    <div className="h-full flex flex-col">
      <Topbar
        episodes={eps}
        slug={slug}
        page={route.page}
        stage={route.stage}
        activeShow={activeShow}
        go={go}
        onPick={(s) => {
          setActiveSlug(s);
          go({ page: "stage", slug: s });
        }}
        onStage={(stage) => go({ page: "stage", slug, stage })}
        onPage={(p) => go({ page: p })}
        onHome={() => go({ page: "stage", slug, stage: "assembly" })}
        onOpenSettings={() => setSettingsOpen(true)}
        onStartTutorial={() => setTourOpen(true)}
      />
      <main className="flex-1 p-3 min-h-0">
        <PageView page={route.page} slug={slug} stage={route.stage} loading={episodes.isLoading} go={go} />
      </main>
      {route.page === "stage" && slug && (
        <ManifestDrawer slug={slug} onJumpToStage={(s) => go({ page: "stage", stage: s as UIStage })} />
      )}
      <LogDrawer />
      <TerminalDrawer />
      <UpdateModal />
      <DiagnosticsModal />
      {settingsOpen && <Settings show={activeShow} onClose={() => setSettingsOpen(false)} />}
      {tourOpen && (
        <Tour
          slug={slug}
          go={go}
          onClose={() => setTourOpen(false)}
          onStartWizard={() => { setTourOpen(false); startWizard(STARTER_SLUG); }}
        />
      )}
      <WizardPanel routedSlug={slug} go={go} />
    </div>
  );
}

function PageView({
  page,
  slug,
  stage,
  loading,
  go,
}: {
  page: Page;
  slug: string;
  stage: UIStage;
  loading: boolean;
  go: (r: any) => void;
}) {
  // Top-level pages — driven by the global activeSlug, not (slug, stage).
  if (page === "docs") {
    return (
      <StageTransition id="docs">
        <Docs />
      </StageTransition>
    );
  }
  if (page === "characters") {
    return (
      <StageTransition id="characters">
        <Characters />
      </StageTransition>
    );
  }

  if (!slug) {
    return (
      <div className="panel p-6 grid place-items-center h-full text-txt-dim">
        {loading ? "Loading episodes…" : "No episodes available."}
      </div>
    );
  }
  return (
    <StageTransition id={`${slug}:${stage}`}>
      <StageView slug={slug} stage={stage} />
    </StageTransition>
  );
}

/** Animates each tab/stage mount. Stages still unmount instantly (their queries
    and SSE hooks tear down as before); only the incoming view is choreographed. */
function StageTransition({ id, children }: { id: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const tween = enterStage(ref.current);
    return () => { tween?.kill(); };
  }, [id]);
  return (
    <div ref={ref} className="h-full min-h-0">
      {children}
    </div>
  );
}

function StageView({ slug, stage }: { slug: string; stage: UIStage }) {
  if (stage === "assembly") return <Assembly slug={slug} />;
  if (stage === "audio") return <Audio slug={slug} />;
  if (stage === "script") return <Script slug={slug} />;
  if (stage === "video") return <Video slug={slug} />;
  if (stage === "graphics") return <Graphics slug={slug} />;
  if (stage === "publish") return <Publish slug={slug} />;
  return <Placeholder slug={slug} stage={stage} />;
}
