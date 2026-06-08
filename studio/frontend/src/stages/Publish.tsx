import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { macuWeb } from "../api/macuweb";
import { youtubeApi, type YtDeviceStart } from "../api/youtube";
import { useStore } from "../store";
import { useT } from "../i18n";

// Stage 6 · Publish — finalize one episode for mayorawesome.com.
export function Publish({ slug }: { slug: string }) {
  const t = useT();
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
  const [reconnect, setReconnect] = useState(false);

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
      pushToast(r.video_id ? t("toast.macuWebVideoSet", { id: r.video_id }) : t("toast.macuWebVideoCleared"), "ok");
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
      pushToast(t("toast.macuWebConnected", { base: r.base }), "ok");
      qc.invalidateQueries({ queryKey: ["macu-web-status"] });
    } catch (e) {
      pushToast(`connect failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    }
  }
  async function publish() {
    setPublishing(true);
    try {
      const r = await macuWeb.publish(activeShow);
      pushToast(
        r.pushed ? t("toast.macuWebPublished", { show: activeShow, files: r.files })
                 : t("toast.macuWebCommitted", { files: r.files }),
        r.pushed ? "ok" : "info",
      );
      // Non-blocking content warnings (macu-web will clamp/skip these — see validate.py).
      const warns = (r as { warnings?: string[] }).warnings ?? [];
      if (warns.length) {
        pushToast(
          `${warns.length} content warning${warns.length === 1 ? "" : "s"}: ` +
            warns.slice(0, 3).join(" · ") + (warns.length > 3 ? " …" : ""),
          "err",
        );
      }
      qc.invalidateQueries({ queryKey: ["macu-web-episode", slug] });
    } catch (e) {
      pushToast(`publish failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally { setPublishing(false); }
  }

  const [device, setDevice] = useState<YtDeviceStart | null>(null);
  async function ytConnect() {
    try {
      const d = await youtubeApi.authStart();
      setDevice(d);
      window.open(d.verification_url, "_blank");
      const poll = setInterval(async () => {
        const p = await youtubeApi.authPoll(d.handle);
        if (p.connected) { clearInterval(poll); setDevice(null); qc.invalidateQueries({ queryKey: ["youtube"] }); pushToast(t("toast.youtubeConnected"), "ok"); }
        else if (p.error) { clearInterval(poll); setDevice(null); pushToast(`YouTube: ${p.error}`, "err"); }
      }, (d.interval || 5) * 1000);
    } catch (e) { pushToast(`YouTube connect: ${e instanceof Error ? e.message : String(e)}`, "err"); }
  }
  const match = matchesQ.data?.matches?.[slug] ?? null;

  const card = "panel p-4 flex flex-col gap-3";
  const lbl = "label-tiny";

  if (!slug) return <div className="panel p-6 text-txt-dim">{t("publish.noEpisode")}</div>;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[860px] flex flex-col gap-4 p-1">
        <div className="flex items-center gap-3">
          <div className="panel-title text-[15px]">{t("stage.publish").toUpperCase()}</div>
          <span className="font-mono text-[12px] text-txt-faint">{slug}</span>
        </div>

        {/* Metadata */}
        <section className={card}>
          <div className="panel-title">{t("publish.metaTitle")}</div>
          <label className="flex flex-col gap-1">
            <span className={lbl}>{t("publish.fieldTitle")}</span>
            <input className="input" value={meta.title}
              onChange={(e) => setMeta({ ...meta, title: e.target.value })}
              onBlur={(e) => e.target.value !== String(m?.title ?? "") && saveMeta({ title: e.target.value })} />
          </label>
          <div className="flex gap-3">
            <label className="flex flex-col gap-1 w-24">
              <span className={lbl}>{t("publish.fieldSeason")}</span>
              <input className="input" type="number" value={meta.season}
                onChange={(e) => setMeta({ ...meta, season: e.target.value })}
                onBlur={(e) => saveMeta({ season: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 w-24">
              <span className={lbl}>{t("publish.fieldEpisode")}</span>
              <input className="input" type="number" value={meta.episode_num}
                onChange={(e) => setMeta({ ...meta, episode_num: e.target.value })}
                onBlur={(e) => saveMeta({ episode_num: e.target.value })} />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className={lbl}>{t("publish.fieldDescription")}</span>
            <textarea className="input min-h-[90px]" value={meta.notes}
              onChange={(e) => setMeta({ ...meta, notes: e.target.value })}
              onBlur={(e) => e.target.value !== String(m?.notes ?? "") && saveMeta({ notes: e.target.value })} />
          </label>
        </section>

        {/* Thumbnail */}
        <section className={card}>
          <div className="panel-title">{t("publish.thumbTitle")}</div>
          {finalQ.data?.thumb_exists ? (
            <img src={mediaUrl.finalThumb(slug)} alt="thumbnail" className="rounded hairline max-w-[320px]" />
          ) : (
            <div className="label-tiny">{t("publish.thumbNone")}</div>
          )}
        </section>

        {/* Hosted video */}
        <section className={card}>
          <div className="panel-title">{t("publish.videoTitle")}</div>
          <p className="label-tiny leading-relaxed">{t("publish.videoHint")}</p>
          <div className="flex gap-2 items-center">
            <input className="input flex-1 font-mono text-[12px]" placeholder={t("publish.videoPlaceholder")}
              value={vid} onChange={(e) => setVid(e.target.value)}
              onBlur={(e) => e.target.value.trim() !== (((m?.youtube as { video_id?: string })?.video_id) ?? "") && saveVid(e.target.value)} />
            {vid && <a className="btn btn-sm" href={`https://youtu.be/${vid}`} target="_blank" rel="noreferrer">{t("publish.open")}</a>}
          </div>

          <div className="hairline-soft border-t pt-3 flex flex-col gap-2">
            <span className={lbl}>{t("publish.ytAccount")}</span>
            {ytAuthQ.data?.connected ? (
              match ? (
                <div className="flex items-center gap-2 text-[12px]">
                  <img src={match.thumbnail} alt="" className="w-16 rounded" />
                  <span className="truncate flex-1">{match.title}</span>
                  <button className="btn btn-sm btn-amber" onClick={() => saveVid(match.video_id)}>{t("publish.ytUseVideo")}</button>
                </div>
              ) : <span className="label-tiny">{t("publish.ytNoMatch")}</span>
            ) : (
              <button className="btn btn-sm" onClick={ytConnect}>
                {device ? t("publish.ytEnterCode", { code: device.user_code }) : t("publish.ytConnect")}
              </button>
            )}
          </div>
        </section>

        {/* macu-web */}
        <section className={card}>
          <div className="panel-title">{t("publish.webTitle")}</div>
          {!connected ? (
            <>
              <p className="label-tiny leading-relaxed">{t("publish.connectHint")}</p>
              <textarea className="input font-mono text-[12px]" rows={2} placeholder="macu-connect.…" value={token} onChange={(e) => setToken(e.target.value)} />
              <button className="btn btn-amber self-start" disabled={!token.trim()} onClick={connect}>{t("publish.connectBtn")}</button>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="label-tiny">{t("publish.connectedTo", { base: statusQ.data?.web || statusQ.data?.base || "" })}</span>
                <button className="btn btn-sm" onClick={() => setReconnect((v) => !v)}>{t("publish.changeConnection")}</button>
              </div>
              {reconnect && (
                <div className="flex flex-col gap-2 border-t hairline-soft pt-3">
                  <p className="label-tiny leading-relaxed">{t("publish.connectHint")}</p>
                  <textarea className="input font-mono text-[12px]" rows={2} placeholder="macu-connect.…" value={token} onChange={(e) => setToken(e.target.value)} />
                  <button className="btn btn-amber self-start" disabled={!token.trim()} onClick={async () => { await connect(); setReconnect(false); }}>{t("publish.connectBtn")}</button>
                </div>
              )}
              <div className="flex items-center gap-3">
                <span className={lbl}>{t("publish.visibility")}</span>
                <select className="input w-40" value={epWebQ.data?.visibility ?? "PRIVATE"} onChange={(e) => setVisibility(e.target.value as "PUBLIC")}>
                  <option value="PUBLIC">{t("publish.visPublic")}</option>
                  <option value="UNLISTED">{t("publish.visUnlisted")}</option>
                  <option value="PRIVATE">{t("publish.visHidden")}</option>
                </select>
                {epWebQ.data?.public && epWebQ.data.url && (
                  <a className="text-[12px] underline text-amber" href={epWebQ.data.url} target="_blank" rel="noreferrer">{t("publish.viewLive")}</a>
                )}
              </div>
              <p className="label-tiny">{t("publish.publishHint")}</p>
              <button className="btn btn-amber self-start" disabled={publishing} onClick={publish}>
                {publishing ? t("publish.publishingBtn") : t("publish.publishBtn", { show: activeShow })}
              </button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
