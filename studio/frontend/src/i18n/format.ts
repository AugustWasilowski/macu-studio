// Pure formatting helpers for the i18n runtime — no React, no state.

export type TParams = { count?: number } & Record<string, string | number>;

// Replace {name} placeholders with params[name]. Unknown placeholders are left as-is
// (so a missing param renders "{foo}" loudly rather than silently dropping text).
export function interpolate(tpl: string, params?: TParams): string {
  if (!params) return tpl;
  return tpl.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
}

const _pr: Record<string, Intl.PluralRules> = {};

// The catalog key for a count in a locale: "<base>.<one|two|few|many|other|zero>".
// Uses the platform's CLDR plural rules — correct per language, zero dependencies.
export function pluralKey(base: string, count: number, locale: string): string {
  let pr = _pr[locale];
  if (!pr) {
    try {
      pr = new Intl.PluralRules(locale);
    } catch {
      pr = new Intl.PluralRules("en");
    }
    _pr[locale] = pr;
  }
  return `${base}.${pr.select(count)}`;
}

export function fmtNumber(n: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale).format(n);
  } catch {
    return String(n);
  }
}

export function fmtDate(ts: number, locale: string, opts?: Intl.DateTimeFormatOptions): string {
  try {
    return new Intl.DateTimeFormat(locale, opts).format(new Date(ts));
  } catch {
    return new Date(ts).toLocaleString();
  }
}
