import { useState } from "react";
import { IChevron } from "./Icons";

/** Collapsible section with a rotating chevron. Extracted from ManifestDrawer's private
 * Section so it can be reused (e.g. the Assembly right rail). When `storageKey` is given,
 * the open/closed state persists in localStorage ("1"/"0") — same idiom Timeline uses for
 * its `macu.tl.*` keys. `bare` skips the inner padding for children that manage their own. */
export function Collapsible({
  title, children, defaultOpen = true, storageKey, bare = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  storageKey?: string;
  bare?: boolean;
}) {
  const [open, setOpen] = useState(() => {
    if (storageKey) {
      const v = localStorage.getItem(storageKey);
      if (v != null) return v !== "0";
    }
    return defaultOpen;
  });
  const toggle = () => setOpen((v) => {
    const next = !v;
    if (storageKey) localStorage.setItem(storageKey, next ? "1" : "0");
    return next;
  });
  return (
    <div className="hairline-soft rounded">
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-bg-2 hover:bg-bg-3"
        onClick={toggle}
      >
        <span style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform .15s" }}>
          <IChevron />
        </span>
        <span className="label-tiny">{title}</span>
      </button>
      {open && (bare ? children : <div className="p-3 flex flex-col gap-2">{children}</div>)}
    </div>
  );
}
