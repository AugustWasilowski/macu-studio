import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { youtubeApi, type YoutubeUpload } from "../api/youtube";
import { useStore } from "../store";
import { Markdown } from "../components/Markdown";
import { useT } from "../i18n";
import { Trans } from "../i18n/Trans";

export function YouTube() {
  const t = useT();
  const activeSlug = useStore((s) => s.activeSlug);
  const setActiveSlug = useStore((s) => s.setActiveSlug);
  const activeShow = useStore((s) => s.activeShow);

  const episodesQ = useQuery({ queryKey: ["episodes", activeShow], queryFn: () => api.episodes(activeShow) });
  const matchesQ = useQuery({ queryKey: ["youtube", "matches"], queryFn: youtubeApi.matches });
  const uploadsQ = useQuery({ queryKey: ["youtube", "uploads"], queryFn: youtubeApi.uploads });

  const eps = episodesQ.data?.episodes ?? [];
  const slug = activeSlug ?? (eps.length ? eps[eps.length - 1].slug : "");

  const scriptQ = useQuery({
    queryKey: ["script", slug],
    queryFn: () => api.script(slug),
    enabled: !!slug,
  });

  const matches = matchesQ.data?.matches ?? {};
  const matched = slug ? matches[slug] : null;
  // "configured" iff the channel returned at least one upload (no creds → []).
  const configured = (uploadsQ.data?.uploads?.length ?? 0) > 0;

  return (
    <div className="grid grid-cols-[280px_1fr_320px] gap-3 h-full min-h-0">
      {/* LEFT — episodes / scripts */}
      <section className="panel flex flex-col min-h-0">
        <header className="px-3 py-2 border-b hairline">
          <div className="panel-title">{t("youtube.panelScripts")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">{t("youtube.episodeCount", { count: eps.length })}</span></div>
        </header>
        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
          {episodesQ.isLoading && <div className="text-txt-faint p-2">{t("common.loading")}</div>}
          {eps.map((e) => {
            const active = e.slug === slug;
            const m = matches[e.slug];
            return (
              <button
                key={e.slug}
                onClick={() => setActiveSlug(e.slug)}
                className={"hairline-soft text-left px-2 py-1.5 rounded transition-colors " + (active ? "border-amber" : "")}
                style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)", background: "var(--bg-2)" } : {}}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[12px]">
                    {e.slug}
                    {e.se_label && <span className="text-cyan ml-1.5">{e.se_label}</span>}
                  </span>
                  {m && <span className="label-tiny text-green" title={t("youtube.matchedTitle")}>● YT</span>}
                </div>
                <div className="text-[12px] text-txt-dim truncate">{e.title}</div>
              </button>
            );
          })}
          {!episodesQ.isLoading && eps.length === 0 && (
            <div className="text-txt-faint p-2">{t("youtube.noEpisodes")}</div>
          )}
        </div>
      </section>

      {/* CENTER — script reader */}
      <section className="panel flex flex-col min-h-0">
        <header className="px-3 py-2 border-b hairline flex items-center justify-between">
          <div className="panel-title">
            {t("youtube.panelReader")}
            {slug && <span className="text-txt-faint normal-case tracking-normal text-[11px]"> / episodes/{slug}/script.md</span>}
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-4 text-[13px] leading-relaxed">
          {!slug ? (
            <div className="text-txt-faint">{t("youtube.selectScript")}</div>
          ) : scriptQ.isLoading ? (
            <div className="text-txt-faint">{t("youtube.loadingScript")}</div>
          ) : scriptQ.data?.text ? (
            <Markdown text={scriptQ.data.text} />
          ) : (
            <div className="text-txt-faint">{t("youtube.noScript", { slug })}</div>
          )}
        </div>
      </section>

      {/* RIGHT — matched YouTube upload */}
      <aside className="panel flex flex-col min-h-0">
        <header className="px-3 py-2 border-b hairline">
          <div className="panel-title">{t("youtube.panelYoutube")}</div>
        </header>
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
          {uploadsQ.isLoading || matchesQ.isLoading ? (
            <div className="text-txt-faint">{t("youtube.loadingUploads")}</div>
          ) : !configured ? (
            <div className="hairline-soft bg-bg-2 rounded p-3 text-[12px] text-txt-dim">
              <div className="label-tiny text-amber mb-1">{t("youtube.notConfiguredLabel")}</div>
              <Trans
                k="youtube.notConfiguredBody"
                tags={[
                  (c) => <code>{c}</code>,
                  (c) => <code>{c}</code>,
                  (c) => <code>{c}</code>,
                ]}
              />
            </div>
          ) : matched ? (
            <UploadCard up={matched} />
          ) : (
            <div className="text-txt-faint text-[12px]">
              {t("youtube.noMatch", { slug })}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function UploadCard({ up }: { up: YoutubeUpload }) {
  const t = useT();
  return (
    <a
      href={up.url}
      target="_blank"
      rel="noopener noreferrer"
      className="hairline-soft rounded overflow-hidden block hover:border-amber transition-colors"
    >
      {up.thumbnail ? (
        <img src={up.thumbnail} alt={up.title} className="w-full block bg-black" style={{ aspectRatio: "16/9", objectFit: "cover" }} />
      ) : (
        <div className="bg-black grid place-items-center" style={{ aspectRatio: "16/9" }}>
          <span className="label-tiny text-txt-faint">{t("youtube.noThumbnail")}</span>
        </div>
      )}
      <div className="p-2 bg-bg-2">
        <div className="text-[12px] font-semibold leading-tight">{up.title}</div>
        <div className="flex items-center gap-2 mt-1">
          <span className="seg-readout">{t("youtube.views", { views: fmtViews(up.view_count) })}</span>
          {up.published_at && (
            <span className="label-tiny text-txt-faint">{up.published_at.slice(0, 10)}</span>
          )}
        </div>
      </div>
    </a>
  );
}

function fmtViews(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}
