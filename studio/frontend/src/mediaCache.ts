// In-memory blob cache for media (audio clips, shot-master webp images),
// populated on demand by the "Pre-cache" buttons on the Audio / Video pages.
// Motivation: media is served with `Cache-Control: no-cache`, so over the
// Cloudflare proxy every <audio>/<img> load pays a revalidation round-trip
// (perceptible lag). Pre-fetching each asset into a Blob + object URL lets
// playback/preview read straight from memory — no network, immune to the proxy.
//
// Freshness: entries are keyed by the exact (mtime-versioned) URL. When an asset
// is regenerated its URL gains a new `?v=<mtime>`, so it misses the stale entry
// and falls back to the network — the fresh asset is served automatically. The
// cache is module-level, so it survives episode switches (switching back is
// instant) and component unmounts.

const cache = new Map<string, string>(); // versioned URL -> object URL

/** Return the cached object URL for an asset if pre-cached, else the URL itself. */
export function resolveMedia(url: string): string {
  return cache.get(url) ?? url;
}

export function isCached(url: string): boolean {
  return cache.has(url);
}

export interface PrecacheProgress {
  done: number;
  total: number;
  failed: number;
}

/**
 * Fetch each URL (that isn't already cached) into a Blob object URL.
 * `cache: "reload"` bypasses the HTTP cache so we capture the current bytes.
 * Runs a small worker pool; never rejects — failures are counted, not thrown.
 */
export async function precacheMedia(
  urls: string[],
  onProgress?: (p: PrecacheProgress) => void,
  concurrency = 4,
): Promise<PrecacheProgress> {
  const todo = urls.filter((u) => !cache.has(u));
  const total = todo.length;
  let done = 0;
  let failed = 0;
  let i = 0;

  async function worker() {
    while (i < todo.length) {
      const url = todo[i++];
      try {
        const r = await fetch(url, { cache: "reload" });
        if (!r.ok) throw new Error(String(r.status));
        const blob = await r.blob();
        cache.set(url, URL.createObjectURL(blob));
      } catch {
        failed++;
      }
      done++;
      onProgress?.({ done, total, failed });
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, total || 1) }, worker),
  );
  return { done, total, failed };
}

/** Revoke all object URLs and empty the cache (frees memory). */
export function clearMediaCache(): void {
  for (const u of cache.values()) URL.revokeObjectURL(u);
  cache.clear();
}
