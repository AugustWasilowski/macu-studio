import { Fragment, ReactNode } from "react";
import { t } from "./index";
import type { TParams } from "./format";

/* Renders a translated string that contains inline markup, for the minority of
   sentences where a fragment must keep distinct styling (a literal path/command).
   The catalog value uses numbered tag placeholders: "<0>…</0>" and {var} slots, e.g.

     "filemenu.shutdown.body": "…start it from a terminal (<0>{cmd}</0>, or the systemd service)."

   Usage:
     <Trans k="filemenu.shutdown.body"
            vars={{ cmd: "./deploy/start-studio.sh" }}
            tags={[(c) => <span className="font-mono">{c}</span>]} />

   The translator only ever moves the opaque <0>…</0> / {var} tokens, so word order
   is owned entirely by the translation (RTL-safe). Anything outside the markers is
   plain translated text. */
export function Trans({
  k,
  vars,
  tags = [],
}: {
  k: string;
  vars?: TParams;
  tags?: ((inner: string) => ReactNode)[];
}) {
  const tpl = t(k); // resolve template (no {var} interpolation yet — done per-segment)
  const out: ReactNode[] = [];
  // Split on either a tag pair <n>inner</n> or a bare {var}. Greedy-safe because tag
  // inner text never contains another tag in our catalogs.
  const re = /<(\d+)>([\s\S]*?)<\/\1>|\{(\w+)\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  const sub = (s: string) => s.replace(/\{(\w+)\}/g, (mm, key) => (vars && key in vars ? String(vars[key]) : mm));
  while ((m = re.exec(tpl))) {
    if (m.index > last) out.push(<Fragment key={i++}>{sub(tpl.slice(last, m.index))}</Fragment>);
    if (m[1] !== undefined) {
      const idx = Number(m[1]);
      const inner = sub(m[2]);
      const render = tags[idx];
      out.push(<Fragment key={i++}>{render ? render(inner) : inner}</Fragment>);
    } else if (m[3] !== undefined) {
      const v = vars && m[3] in vars ? String(vars[m[3]]) : m[0];
      out.push(<Fragment key={i++}>{v}</Fragment>);
    }
    last = re.lastIndex;
  }
  if (last < tpl.length) out.push(<Fragment key={i++}>{sub(tpl.slice(last))}</Fragment>);
  return <>{out}</>;
}
