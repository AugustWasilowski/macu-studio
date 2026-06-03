import { IPlay, IPause } from "./Icons";

export function PlayBtn({ playing, onClick, title }: { playing: boolean; onClick: () => void; title?: string }) {
  return (
    <button
      onClick={onClick}
      title={title ?? (playing ? "Pause" : "Play")}
      className="w-7 h-7 grid place-items-center rounded-[3px] border"
      style={{
        background: playing ? "rgba(51,255,102,0.10)" : "var(--bg-2)",
        color: playing ? "var(--green)" : "var(--txt)",
        borderColor: playing ? "rgba(51,255,102,0.45)" : "var(--line-soft)",
        boxShadow: playing ? "0 0 6px rgba(51,255,102,.4)" : undefined,
      }}
    >
      {playing ? <IPause /> : <IPlay />}
    </button>
  );
}
