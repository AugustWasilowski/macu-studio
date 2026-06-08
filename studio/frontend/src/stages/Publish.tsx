import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { macuWeb } from "../api/macuweb";
import { youtubeApi, type YtDeviceStart } from "../api/youtube";
import { useStore } from "../store";

// Stage 6 · Publish — finalize one episode for mayorawesome.com.
export function Publish({ slug }: { slug: string }) {
  const pushToast = useStore((s) => s.pushToast);
  const activeShow = useStore((s) => s.activeShow);
  const qc = useQueryClient();

  const manifestQ = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug), enabled: !!slug });
  const finalQ = useQuery({ queryKey: ["final", slug], queryFn: () => api.final(slug), enabled: !!slug });
  const statusQ = useQuery({ queryKey: ["macu-web-status"], queryFn: macuWeb.status });
  const connected = !!statusQ.data?.connected;
  const epWebQ = useQuery({
    queryKey: ["macu-web-episode", slug],
    queryFn: () => macuWeb.episodeStatus(slug),
    enabled: !!slug && connected,
    retry: false,
  });
  const ytAuthQ = useQuery({ queryKey: ["youtube", "auth"], queryFn: youtubeApi.auth });
  const matchesQ = useQuery({ queryKey: ["youtube", "matches"], queryFn: youtubeApi.matches, enabled: !!ytAuthQ.data?.connected });

  const m = manifestQ.data as Record<string, unknown> | undefined;
  const [meta, setMeta] = useState({ title: "", season: "", episode_num: "", notes: "" });
  const [vid, setVid] = useState("");
  const [token, setToken] = useState("");
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    if (!m) return;
    const yt = (m.youtube as { video_id?: string } | undefined) ?? {};
    setMeta({
      title: String(m.title ?? ""),
      season: m.season == null ? "" : String(m.season),
      episode_num: m.episode_num == null ? "" : String(m.episode_num),
      notes: String(m.notes ?? ""),
    });
    setVid(yt.video_id ?? "");
  }, [slug, manifestQ.dataUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveMeta(patch: Record<string, string>) {
    try {
      await macuWeb.setMeta(slug, patch);
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["episodes"] });
    } catch (e) {
      pushToast(`${slug}: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }
  async function saveVid(raw: string) {
    try {
      const r = await macuWeb.setVideoId(slug, raw.trim());
      setVid(r.video_id ?? "");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      pushToast(r.video_id ? `video set (${r.video_id})` : "video cleared", "ok");
    } catch (e) {
      pushToast(`${slug}: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }
  async function setVisibility(v: "PUBLIC" | "UNLISTED" | "PRIVATE") {
    try {
      await macuWeb.setVisibility(slug, v);
      qc.invalidateQueries({ queryKey: ["macu-web-episode", slug] });
    } catch (e) {
      pushToast(`visibility: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }
  async function connect() {
    try {
      const r = await macuWeb.connect(token.trim());
      setToken("");
      pushToast(`Connected to ${r.base}`, "ok");
      qc.invalidateQueries({ queryKey: ["macu-web-status"] });
    } catch (e) {
      pushToast(`connect failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }
  async function publish() {
    setPublishing(true);
    try {
      const r = await macuWeb.publish(activeShow);
      pushToast(r.pushed ? `Published ${activeShow} (${r.files} files)` : `committed locally (${r.files})`, r.pushed ? "ok" : "info");
      qc.invalidateQueries({ queryKey: ["macu-web-episode", slug] });
    } catch (e) {
      pushToast(`publish failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setPublishing(false); }
  }

  // YouTube device-flow connect
  const [device, setDevice] = useState<YtDeviceStart | null>(null);
  async function ytConnect() {
    try {
      const d = await youtubeApi.authStart();
      setDevice(d);
      window.open(d.verification_url, "_blank");
      const poll = setInterval(async () => {
        const p = await youtubeApi.authPoll(d.handle);
        if (p.connected) { clearInterval(poll); setDevice(null); qc.invalidateQueries({ queryKey: ["youtube"] }); pushToast("YouTube connected", "ok"); }
        else if (p.error) { clearInterval(poll); setDevice(null); pushToast(`YouTube: ${p.error}`, "err"); }
      }, (d.interval || 5) * 1000);
    } catch (e) { pushToast(`YouTube connect: ${e instanceof Error ? e.message : String(e)}`, "err"); }
  }
  const match = matchesQ.data?.matches?.[slug] ?? null;

  const card = "panel p-4 flex flex-col gap-3";
  const lbl = "label-tiny";

  if (!slug) return <div className="panel p-6 text-txt-dim">No episode selected.</div>;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[860px] flex flex-col gap-4 p-1">
        <div className="flex items-center gap-3">
          <div className="panel-title text-[15px]">PUBLISH</div>
          <span className="font-mono text-[12px] text-txt-faint">{slug}</span>
        </div>

        {/* Metadata */}
        <section className={card}>
          <div className="panel-title">Episode metadata</div>
          <label className="flex flex-col gap-1">
            <span className={lbl}>Title</span>
            <input className="input" value={meta.title}
              onChange={(e) => setMeta({ ...meta, title: e.target.value })}
              onBlur={(e) => e.target.value !== String(m?.title ?? "") && saveMeta({ title: e.target.value })} />
          </label>
          <div className="flex gap-3">
            <label className="flex flex-col gap-1 w-24">
              <span className={lbl}>Season</span>
              <input className="input" type="number" value={meta.season}
                onChange={(e) => setMeta({ ...meta, season: e.target.value })}
                onBlur={(e) => saveMeta({ season: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 w-24">
              <span className={lbl}>Episode #</span>
              <input className="input" type="number" value={meta.episode_num}
                onChange={(e) => setMeta({ ...meta, episode_num: e.target.value })}
                onBlur={(e) => saveMeta({ episode_num: e.target.value })} />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className={lbl}>Description (shown on the episode page)</span>
            <textarea className="input min-h-[90px]" value={meta.notes}
              onChange={(e) => setMeta({ ...meta, notes: e.target.value })}
              onBlur={(e) => e.target.value !== String(m?.notes ?? "") && saveMeta({ notes: e.target.value })} />
          </label>
        </section>

        {/* Thumbnail */}
        <section className={card}>
          <div className="panel-title">Thumbnail</div>
          {finalQ.data?.thumb_exists ? (
            <img src={mediaUrl.finalThumb(slug)} alt="thumbnail" className="rounded hairline max-w-[320px]" />
          ) : (
            <div className="label-tiny">No rendered thumbnail yet — run the render (stage 5) first.</div>
          )}
        </section>

        {/* Hosted video */}
        <section className={card}>
          <div className="panel-title">Hosted video</div>
          <p className="label-tiny leading-relaxed">macu-web doesn&apos;t host video — paste the link to where it lives (YouTube). It embeds on the episode page.</p>
          <div className="flex gap-2 items-center">
            <input className="input flex-1 font-mono text-[12px]" placeholder="YouTube ID or URL"
              value={vid} onChange={(e) => setVid(e.target.value)}
              onBlur={(e) => e.target.value.trim() !== (((m?.youtube as { video_id?: string })?.video_id) ?? "") && saveVid(e.target.value)} />
            {vid && <a className="btn btn-sm" href={`https://youtu.be/${vid}`} target="_blank" rel="noreferrer">open ↗</a>}
          </div>

          <div className="hairline-soft border-t pt-3 flex flex-col gap-2">
            <span className={lbl}>YouTube account</span>
            {ytAuthQ.data?.connected ? (
              <>
                {match ? (
                  <div className="flex items-center gap-2 text-[12px]">
                    <img src={match.thumbnail} alt="" className="w-16 rounded" />
                    <span className="truncate flex-1">{match.title}</span>
                    <button className="btn btn-sm btn-amber" onClick={() => saveVid(match.video_id)}>Use this video</button>
                  </div>
                ) : <span className="label-tiny">No channel match for this episode title.</span>}
              </>
            ) : (
              <button className="btn btn-sm" onClick={ytConnect}>
                {device ? `Enter code ${device.user_code}…` : "Connect YouTube account"}
              </button>
            )}
          </div>
        </section>

        {/* macu-web */}
        <section className={card}>
          <div className="panel-title">mayorawesome.com</div>
          {!connected ? (
            <>
              <p className="label-tiny leading-relaxed">Paste your connect token (Manage page on mayorawesome.com → Connect MACU Studio).</p>
              <textarea className="input font-mono text-[12px]" rows={2} placeholder="macu-connect.…" value={token} onChange={(e) => setToken(e.target.value)} />
              <button className="btn btn-amber self-start" disabled={!token.trim()} onClick={connect}>Connect</button>
            </>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <span className={lbl}>Visibility</span>
                <select className="input w-40" value={epWebQ.data?.visibility ?? "PRIVATE"} onChange={(e) => setVisibility(e.target.value as "PUBLIC")}>
                  <option value="PUBLIC">Public</option>
                  <option value="UNLISTED">Unlisted</option>
                  <option value="PRIVATE">Hidden</option>
                </select>
                {epWebQ.data?.public && epWebQ.data.url && (
                  <a className="text-[12px] underline text-amber" href={epWebQ.data.url} target="_blank" rel="noreferrer">view live page ↗</a>
                )}
              </div>
              <p className="label-tiny">Edit fields above, then publish to push them to the site.</p>
              <button className="btn btn-amber self-start" disabled={publishing} onClick={publish}>
                {publishing ? "Publishing…" : `Publish ${activeShow}`}
              </button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
