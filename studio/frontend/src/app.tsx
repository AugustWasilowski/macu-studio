import { useEffect } from "react";
import { useQuery, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "./api";
import { Topbar } from "./components/Topbar";
import { Toasts } from "./components/Toasts";
import { Assembly } from "./stages/Assembly";
import { Audio } from "./stages/Audio";
import { Script } from "./stages/Script";
import { Video } from "./stages/Video";
import { Graphics } from "./stages/Graphics";
import { Placeholder } from "./stages/Placeholder";
import { ManifestDrawer } from "./components/ManifestDrawer";
import { useRoute } from "./route";
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
  const episodes = useQuery({ queryKey: ["episodes"], queryFn: api.episodes });

  // Default to a slug once we know what's available
  useEffect(() => {
    if (!route.slug && episodes.data?.episodes.length) {
      const pick = episodes.data.episodes.find((e) => e.slug === "ep18")
        ?? episodes.data.episodes[episodes.data.episodes.length - 1];
      go({ slug: pick.slug, stage: route.stage });
    }
  }, [episodes.data, route.slug, route.stage, go]);

  const eps = episodes.data?.episodes ?? [];

  return (
    <div className="h-full flex flex-col">
      <Topbar
        episodes={eps}
        slug={route.slug}
        stage={route.stage}
        onPick={(slug) => go({ slug })}
        onStage={(stage) => go({ stage })}
      />
      <main className="flex-1 p-3 min-h-0">
        {!route.slug ? (
          <div className="panel p-6 grid place-items-center h-full text-txt-dim">
            {episodes.isLoading ? "Loading episodes…" : "No episodes available."}
          </div>
        ) : (
          <StageView slug={route.slug} stage={route.stage} />
        )}
      </main>
      {route.slug && <ManifestDrawer slug={route.slug} onJumpToStage={(s) => go({ stage: s as any })} />}
    </div>
  );
}

function StageView({ slug, stage }: { slug: string; stage: UIStage }) {
  if (stage === "assembly") return <Assembly slug={slug} />;
  if (stage === "audio") return <Audio slug={slug} />;
  if (stage === "script") return <Script slug={slug} />;
  if (stage === "video") return <Video slug={slug} />;
  if (stage === "graphics") return <Graphics slug={slug} />;
  return <Placeholder slug={slug} stage={stage} />;
}
