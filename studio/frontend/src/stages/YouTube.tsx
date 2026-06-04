import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { youtubeApi, type YoutubeUpload } from "../api/youtube";
import { useStore } from "../store";
import { Markdown } from "../components/Markdown";

export function YouTube() {
  const activeSlug = useStore((s) => s.activeSlug);
  const setActiveSlug = useStore((s) => s.setActiveSlug);

  const episodesQ = useQuery({ queryKey: ["episodes"], queryFn: api.episodes });
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
          <div className="panel-title">SCRIPTS <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {eps.length} episodes</span></div>
        </header>
        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
          {episodesQ.isLoading && <div className="text-txt-faint p-2">Loading…</div>}
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
                  <span className="font-mono text-[12px]">{e.slug}</span>
                  {m && <span className="label-tiny text-green" title="matched YouTube upload">● YT</span>}
                </div>
                <div className="text-[12px] text-txt-dim truncate">{e.title}</div>
              </button>
            );
          })}
          {!episodesQ.isLoading && eps.length === 0 && (
            <div className="text-txt-faint p-2">No episodes.</div>
          )}
        </div>
      </section>

      {/* CENTER — script reader */}
      <section className="panel flex flex-col min-h-0">
        <header className="px-3 py-2 border-b hairline flex items-center justify-between">
          <div className="panel-title">
            READER
            {slug && <span className="text-txt-faint normal-case tracking-normal text-[11px]"> / episodes/{slug}/script.md</span>}
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-4 text-[13px] leading-relaxed">
          {!slug ? (
            <div className="text-txt-faint">Select a script on the left.</div>
          ) : scriptQ.isLoading ? (
            <div className="text-txt-faint">Loading script…</div>
          ) : scriptQ.data?.text ? (
            <Markdown text={scriptQ.data.text} />
          ) : (
            <div className="text-txt-faint">No script.md for {slug}.</div>
          )}
        </div>
      </section>

      {/* RIGHT — matched YouTube upload */}
      <aside className="panel flex flex-col min-h-0">
        <header className="px-3 py-2 border-b hairline">
          <div className="panel-title">YOUTUBE</div>
        </header>
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
          {uploadsQ.isLoading || matchesQ.isLoading ? (
            <div className="text-txt-faint">Loading uploads…</div>
          ) : !configured ? (
            <div className="hairline-soft bg-bg-2 rounded p-3 text-[12px] text-txt-dim">
              <div className="label-tiny text-amber mb-1">YOUTUBE NOT CONFIGURED</div>
              Add an API key + channel id to
              <code> ~/.config/macu-studio/youtube.json</code> (or set
              <code> YOUTUBE_API_KEY</code> / <code>YOUTUBE_CHANNEL_ID</code>) to
              show matched uploads here.
            </div>
          ) : matched ? (
            <UploadCard up={matched} />
          ) : (
            <div className="text-txt-faint text-[12px]">
              No matched upload for <span className="font-mono">{slug}</span>.
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function UploadCard({ up }: { up: YoutubeUpload }) {
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
          <span className="label-tiny text-txt-faint">no thumbnail</span>
        </div>
      )}
      <div className="p-2 bg-bg-2">
        <div className="text-[12px] font-semibold leading-tight">{up.title}</div>
        <div className="flex items-center gap-2 mt-1">
          <span className="seg-readout">{fmtViews(up.view_count)} VIEWS</span>
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
