import { useRef, useState } from "react";
import { INote, IRegen } from "./Icons";
import { Popover } from "./Popover";

export function RegenNotes({
  onSubmit, placeholder = "guidance for the pipeline…", seedNote,
}: {
  onSubmit: (text: string) => void;
  placeholder?: string;
  seedNote?: string;
}) {
  const [open, setOpen] = useState(false);
  const [txt, setTxt] = useState(seedNote ?? "");
  const btn = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | undefined>();

  function toggle() {
    if (!open && btn.current) {
      const r = btn.current.getBoundingClientRect();
      setAnchor({ top: r.bottom + 4, left: Math.max(8, r.right - 300) });
    }
    setOpen((o) => !o);
  }

  return (
    <span className="inline-block">
      <button
        ref={btn}
        className="btn p-1"
        title="Regenerate with notes…"
        onClick={toggle}
      >
        <INote />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} title="Regenerate with notes" width={300} anchor={anchor}>
        <textarea
          className="input w-full"
          style={{ height: 80, resize: "vertical" }}
          value={txt}
          placeholder={placeholder}
          onChange={(e) => setTxt(e.target.value)}
        />
        <div className="flex justify-end gap-2 mt-2">
          <button className="btn" onClick={() => setOpen(false)}>Cancel</button>
          <button
            className="btn btn-amber"
            onClick={() => { onSubmit(txt); setOpen(false); }}
          >
            <IRegen /> Regen
          </button>
        </div>
      </Popover>
    </span>
  );
}
