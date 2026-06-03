import { Dot } from "./Badge";
import { IRegen } from "./Icons";
import type { AssetStatus } from "../types";

export interface FieldProps {
  label: string;
  value: string | number;
  onChange?: (v: string) => void;
  type?: "text" | "number" | "checkbox";
  suffix?: string;
  dot?: AssetStatus | string;
  onRegen?: () => void;
  options?: string[];
  placeholder?: string;
  monospace?: boolean;
  rows?: number;
}

export function Field(p: FieldProps) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label-tiny flex items-center gap-1.5">
        {p.label}
        {p.dot && <Dot status={p.dot} />}
      </span>
      <span className="flex items-center gap-1.5">
        {p.options ? (
          <select
            className="input flex-1"
            value={String(p.value)}
            onChange={(e) => p.onChange?.(e.target.value)}
          >
            {p.options.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        ) : p.rows && p.rows > 1 ? (
          <textarea
            className="input flex-1 py-1.5"
            style={{ height: p.rows * 18 + 8, resize: "vertical", whiteSpace: "pre-wrap" }}
            value={String(p.value)}
            placeholder={p.placeholder}
            onChange={(e) => p.onChange?.(e.target.value)}
          />
        ) : (
          <input
            className="input flex-1"
            type={p.type ?? "text"}
            value={p.type === "checkbox" ? undefined : String(p.value)}
            checked={p.type === "checkbox" ? Boolean(p.value) : undefined}
            placeholder={p.placeholder}
            onChange={(e) =>
              p.onChange?.(p.type === "checkbox" ? String((e.target as HTMLInputElement).checked) : e.target.value)
            }
          />
        )}
        {p.suffix && <span className="label-tiny pl-1">{p.suffix}</span>}
        {p.onRegen && (
          <button className="btn p-1" title="Regenerate" onClick={p.onRegen}>
            <IRegen />
          </button>
        )}
      </span>
    </label>
  );
}
