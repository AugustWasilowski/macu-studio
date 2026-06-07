import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { youtubeApi, type YoutubeUpload, type YtDeviceStart } from "../api/youtube";
import { useStore } from "../store";
import { Markdown } from "../components/Markdown";
import { useT, LOCALES } from "../i18n";
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
            <>
              <UploadCard up={matched} />
              <CaptionsPanel slug={slug} />
            </>
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

function langLabel(code: string): string {
  if (code === "en") return "English";
  const l = LOCALES.find((x) => x.code === code);
  return l ? `${l.nativeName} (${l.englishName})` : code;
}

/* Caption tracks for the matched video: connect YouTube (OAuth device flow) once,
   then upload the episode's English + translated SRTs as caption tracks. */
function CaptionsPanel({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const cap = useQuery({ queryKey: ["yt-captions", slug], queryFn: () => youtubeApi.captions(slug), enabled: !!slug });

  const [cid, setCid] = useState("");
  const [csec, setCsec] = useState("");
  const [device, setDevice] = useState<YtDeviceStart | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const refresh = () => qc.invalidateQueries({ queryKey: ["yt-captions", slug] });

  // Poll the device flow until approved / errored.
  useEffect(() => {
    if (!device) return;
    pollRef.current = setInterval(async () => {
      try {
        const r = await youtubeApi.authPoll(device.handle);
        if (r.connected) { clearInterval(pollRef.current); setDevice(null); push(t("youtube.captions.connected"), "ok"); refresh(); }
        else if (r.error) { clearInterval(pollRef.current); setDevice(null); push(r.error, "err"); }
      } catch { /* keep polling */ }
    }, Math.max(3, device.interval) * 1000);
    return () => clearInterval(pollRef.current);
  }, [device]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveClient() {
    setBusy(true);
    try { await youtubeApi.setClient(cid.trim(), csec.trim()); refresh(); }
    catch (e) { push(e instanceof Error ? e.message : String(e), "err"); }
    finally { setBusy(false); }
  }
  async function connect() {
    setBusy(true);
    try { setDevice(await youtubeApi.authStart()); }
    catch (e) { push(e instanceof Error ? e.message : String(e), "err"); }
    finally { setBusy(false); }
  }
  async function disconnect() {
    await youtubeApi.disconnect(); refresh();
  }
  async function upload(langs?: string[]) {
    setBusy(true);
    try {
      const r = await youtubeApi.uploadCaptions(slug, langs);
      const ok = r.results.filter((x) => x.action !== "error").length;
      const bad = r.results.filter((x) => x.action === "error");
      push(t("youtube.captions.uploaded", { n: ok }), bad.length ? "info" : "ok");
      bad.forEach((b) => push(`${b.lang}: ${b.error}`, "err"));
      refresh();
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e);
      push(m, "err");
    } finally { setBusy(false); }
  }

  const d = cap.data;
  const existingLangs = new Set((d?.existing ?? []).map((x) => x.language));

  return (
    <div className="hairline-soft rounded p-3 flex flex-col gap-2 bg-bg-2">
      <div className="panel-title">{t("youtube.captions.title")}</div>

      {cap.isLoading ? (
        <div className="label-tiny text-txt-faint">{t("common.loading")}</div>
      ) : !d?.has_client ? (
        /* one-time: paste the OAuth client */
        <div className="flex flex-col gap-2">
          <p className="label-tiny leading-relaxed">{t("youtube.captions.clientHelp")}</p>
          <input className="input" placeholder={t("youtube.captions.clientId")} value={cid} onChange={(e) => setCid(e.target.value)} />
          <input className="input" placeholder={t("youtube.captions.clientSecret")} type="password" value={csec} onChange={(e) => setCsec(e.target.value)} />
          <button className="btn btn-amber justify-center" disabled={busy || !cid.trim() || !csec.trim()} onClick={saveClient}>{t("common.save")}</button>
        </div>
      ) : device ? (
        /* device-flow waiting */
        <div className="flex flex-col gap-2 items-center text-center py-2">
          <p className="label-tiny">{t("youtube.captions.deviceGo")}</p>
          <a className="text-cyan text-[13px] underline" href={device.verification_url} target="_blank" rel="noopener noreferrer">{device.verification_url}</a>
          <div className="text-amber font-mono text-2xl tracking-widest">{device.user_code}</div>
          <div className="label-tiny text-txt-faint">{t("youtube.captions.waiting")}</div>
          <button className="btn" onClick={() => { clearInterval(pollRef.current); setDevice(null); }}>{t("common.cancel")}</button>
        </div>
      ) : !d?.connected ? (
        <div className="flex flex-col gap-2">
          <button className="btn btn-amber justify-center" disabled={busy} onClick={connect}>{t("youtube.captions.connectBtn")}</button>
        </div>
      ) : !d?.video_id ? (
        <div className="label-tiny text-txt-faint">{t("youtube.captions.noVideo")}</div>
      ) : d.available.length === 0 ? (
        <div className="label-tiny text-txt-faint">{t("youtube.captions.noTracks")}</div>
      ) : (
        /* connected + tracks available */
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            {d.available.map((a) => {
              const on = existingLangs.has(a.lang === "en" ? "en" : a.lang);
              return (
                <div key={a.lang} className="flex items-center gap-2 text-[12px]">
                  <span className="flex-1 truncate">{langLabel(a.lang)}</span>
                  {on && <span className="label-tiny text-green">{t("youtube.captions.onYoutube")}</span>}
                  <button className="btn p-1 label-tiny" disabled={busy} onClick={() => upload([a.lang])}>{t("youtube.captions.upload")}</button>
                </div>
              );
            })}
          </div>
          <button className="btn btn-amber justify-center" disabled={busy} onClick={() => upload()}>
            {busy ? t("youtube.captions.uploading") : t("youtube.captions.uploadAll")}
          </button>
          <p className="label-tiny opacity-60 leading-relaxed">{t("youtube.captions.quotaNote")}</p>
          <button className="label-tiny text-txt-faint hover:text-red self-start" onClick={disconnect}>{t("youtube.captions.disconnect")}</button>
        </div>
      )}
    </div>
  );
}
