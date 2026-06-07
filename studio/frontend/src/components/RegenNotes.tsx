import { useRef, useState } from "react";
import { useT } from "../i18n";
import { INote, IRegen } from "./Icons";
import { Popover } from "./Popover";

export function RegenNotes({
  onSubmit, placeholder, seedNote,
}: {
  onSubmit: (text: string) => void;
  placeholder?: string;
  seedNote?: string;
}) {
  const t = useT();
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
        title={t("regennotes.buttonTitle")}
        onClick={toggle}
      >
        <INote />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} title={t("regennotes.popoverTitle")} width={300} anchor={anchor}>
        <textarea
          className="input w-full"
          style={{ height: 80, resize: "vertical" }}
          value={txt}
          placeholder={placeholder ?? t("regennotes.placeholder")}
          onChange={(e) => setTxt(e.target.value)}
        />
        <div className="flex justify-end gap-2 mt-2">
          <button className="btn" onClick={() => setOpen(false)}>{t("common.cancel")}</button>
          <button
            className="btn btn-amber"
            onClick={() => { onSubmit(txt); setOpen(false); }}
          >
            <IRegen /> {t("regennotes.regen")}
          </button>
        </div>
      </Popover>
    </span>
  );
}
