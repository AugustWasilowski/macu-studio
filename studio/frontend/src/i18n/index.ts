// Lightweight i18n runtime. English is bundled and is the source-of-truth fallback;
// other locales are lazy-loaded JSON catalogs (Vite code-splits each via the glob
// below). Mirrors the shape of src/theme.ts (applyX / currentX) and is driven by the
// Zustand `locale` field for re-rendering (see useT + store.ts setLocale).
import { useMemo } from "react";
import { useStore } from "../store";
import en from "./locales/en.json";
import { interpolate, pluralKey, fmtNumber, fmtDate, TParams } from "./format";
import { LOCALES, dirOf } from "./locales";

export type Catalog = Record<string, string>;
export { LOCALES, dirOf };
export type { TParams };

const EN = en as Catalog;

// One dynamic-import loader per non-English catalog; resolved on demand.
const _loaders = import.meta.glob<{ default: Catalog }>("./locales/*.json");

let _locale = "en";
let _active: Catalog = EN;
const _cache: Record<string, Catalog> = { en: EN };

async function loadCatalog(code: string): Promise<Catalog> {
  if (_cache[code]) return _cache[code];
  const loader = _loaders[`./locales/${code}.json`];
  if (!loader) {
    _cache[code] = EN; // unknown locale → English
    return EN;
  }
  try {
    const mod = await loader();
    const cat = (mod.default ?? (mod as unknown)) as Catalog;
    _cache[code] = cat;
    return cat;
  } catch {
    _cache[code] = EN;
    return EN;
  }
}

export function currentLocale(): string {
  return localStorage.getItem("macu.locale") || "en";
}

// Load a catalog and apply it document-wide (lang + dir). Awaited by store.setLocale
// BEFORE flipping the store's `locale`, so the re-render reads a populated catalog.
export async function applyLocale(code: string): Promise<void> {
  const cat = await loadCatalog(code);
  _locale = code;
  _active = cat;
  const root = document.documentElement;
  root.lang = code;
  root.dir = dirOf(code);
}

export function activeLocale(): string {
  return _locale;
}

function lookup(key: string): string {
  return _active[key] ?? EN[key] ?? key;
}

// Translate a key. Pass {count} to pluralize (resolves "<key>.<category>"), and any
// other {name} values to interpolate. Safe to call outside React (toasts) — it reads
// the module-level active catalog set by applyLocale.
export function t(key: string, params?: TParams): string {
  if (params && typeof params.count === "number") {
    const pk = pluralKey(key, params.count, _locale);
    const tpl = _active[pk] ?? EN[pk] ?? _active[`${key}.other`] ?? EN[`${key}.other`] ?? lookup(key);
    return interpolate(tpl, params);
  }
  return interpolate(lookup(key), params);
}

// React hook: returns a `t` that's a fresh identity whenever the locale changes, so
// components subscribing via this hook re-render on language switch.
export function useT(): typeof t {
  const locale = useStore((s) => s.locale);
  return useMemo(() => {
    void locale;
    return t;
  }, [locale]);
}

// Locale-aware number/date formatting bound to the current locale.
export function n(value: number): string {
  return fmtNumber(value, _locale);
}
export function d(ts: number, opts?: Intl.DateTimeFormatOptions): string {
  return fmtDate(ts, _locale, opts);
}
