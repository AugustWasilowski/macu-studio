import { useEffect, useState } from "react";
import { useQuery, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "./api";
import { Topbar } from "./components/Topbar";
import { Settings } from "./components/Settings";
import { Toasts } from "./components/Toasts";
import { Assembly } from "./stages/Assembly";
import { Audio } from "./stages/Audio";
import { Script } from "./stages/Script";
import { Video } from "./stages/Video";
import { Graphics } from "./stages/Graphics";
import { YouTube } from "./stages/YouTube";
import { Docs } from "./stages/Docs";
import { Placeholder } from "./stages/Placeholder";
import { ManifestDrawer } from "./components/ManifestDrawer";
import { LogDrawer } from "./components/LogDrawer";
import { TerminalDrawer } from "./components/TerminalDrawer";
import { useRoute, Page } from "./route";
import { useStore } from "./store";
import { UIStage } from "./types";

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
  const [route, go] = useRoute();
  const activeSlug = useStore((s) => s.activeSlug);
  const setActiveSlug = useStore((s) => s.setActiveSlug);
  const activeShow = useStore((s) => s.activeShow);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const pushToast = useStore((s) => s.pushToast);
  const episodes = useQuery({
    queryKey: ["episodes", activeShow],
    queryFn: () => api.episodes(activeShow),
    refetchInterval: 5000,        // keep the picker's git-sync dots fresh as files change
    refetchOnWindowFocus: true,
  });

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
      const pick = eps.find((e) => e.slug === "ep-018") ?? eps[eps.length - 1];
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
        onStartTutorial={() => pushToast("tutorial coming next", "info")}
      />
      <main className="flex-1 p-3 min-h-0">
        <PageView page={route.page} slug={slug} stage={route.stage} loading={episodes.isLoading} go={go} />
      </main>
      {route.page === "stage" && slug && (
        <ManifestDrawer slug={slug} onJumpToStage={(s) => go({ page: "stage", stage: s as UIStage })} />
      )}
      <LogDrawer />
      <TerminalDrawer />
      {settingsOpen && <Settings show={activeShow} onClose={() => setSettingsOpen(false)} />}
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
  if (page === "youtube") return <YouTube />;
  if (page === "docs") return <Docs />;

  if (!slug) {
    return (
      <div className="panel p-6 grid place-items-center h-full text-txt-dim">
        {loading ? "Loading episodes…" : "No episodes available."}
      </div>
    );
  }
  return <StageView slug={slug} stage={stage} />;
}

function StageView({ slug, stage }: { slug: string; stage: UIStage }) {
  if (stage === "assembly") return <Assembly slug={slug} />;
  if (stage === "audio") return <Audio slug={slug} />;
  if (stage === "script") return <Script slug={slug} />;
  if (stage === "video") return <Video slug={slug} />;
  if (stage === "graphics") return <Graphics slug={slug} />;
  return <Placeholder slug={slug} stage={stage} />;
}
