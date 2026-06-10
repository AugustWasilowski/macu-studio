import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useStore } from "../store";
import type { Manifest, Cue, TitleAsset, Shot, FinalInfo } from "../types";
import type { WizardGate } from "./wizard";

export interface GateResult {
  done: boolean;
  detail?: string; // optional progress hint, e.g. "3/5 rendered"
}

const POLL = 4000; // safety net for actions taken outside the wizard's view (MCP, CLI, another tab)

// Subscribe to the SAME React Query keys the stage pages use (so the cache is shared and the
// wizard sees the same data the page does). Only the query for the *active* gate is enabled.
export function useWizardGates(slug: string, gate: WizardGate | undefined): GateResult {
  const activeShow = useStore((s) => s.activeShow);
  const run = useStore((s) => (slug ? s.runs[slug] : undefined));
  const has = (g: WizardGate) => gate === g && !!slug;

  const episodesQ = useQuery({
    queryKey: ["episodes", activeShow],
    queryFn: () => api.episodes(activeShow),
    enabled: has("episodeExists"),
    refetchInterval: POLL,
  });
  const manifestGate = gate === "manifestHasCues" || gate === "speakersCast" || gate === "sfxPlaced";
  const manifestQ = useQuery({
    queryKey: ["manifest", slug],
    queryFn: () => api.manifest(slug),
    enabled: manifestGate && !!slug,
    refetchInterval: POLL,
  });
  const cuesQ = useQuery({
    queryKey: ["cues", slug],
    queryFn: () => api.cues(slug),
    enabled: has("voAllRendered"),
    refetchInterval: POLL,
  });
  const titlesQ = useQuery({
    queryKey: ["titles", slug],
    queryFn: () => api.titles(slug),
    enabled: has("titleRendered"),
    refetchInterval: POLL,
  });
  const shotsQ = useQuery({
    queryKey: ["shots", slug],
    queryFn: () => api.shots(slug),
    enabled: has("shotRendered"),
    refetchInterval: POLL,
  });
  const finalQ = useQuery({
    queryKey: ["final", slug],
    queryFn: () => api.final(slug),
    enabled: has("finalExists"),
    refetchInterval: POLL,
  });

  switch (gate) {
    case "episodeExists":
      return { done: !!episodesQ.data?.episodes.some((e) => e.slug === slug) };

    case "manifestHasCues": {
      const m = manifestQ.data as Manifest | undefined;
      return { done: (m?.cues?.length ?? 0) > 0 };
    }

    case "speakersCast": {
      const m = manifestQ.data as Manifest | undefined;
      const speakers = new Set(
        (m?.cues ?? []).map((c) => c.speaker).filter((s): s is string => !!s),
      );
      const mapped = m?.voice?.speaker_map ?? {};
      const total = speakers.size;
      const ok = total > 0 && [...speakers].every((s) => s in mapped);
      const have = [...speakers].filter((s) => s in mapped).length;
      return { done: ok, detail: total ? `${have}/${total}` : undefined };
    }

    case "sfxPlaced": {
      const m = manifestQ.data as Manifest | undefined;
      return { done: (m?.sfx?.length ?? 0) > 0 };
    }

    case "voAllRendered": {
      const cues: Cue[] = cuesQ.data?.cues ?? [];
      const total = cues.length;
      const made = cues.filter((c) => c.status === "generated").length;
      return { done: total > 0 && made === total, detail: total ? `${made}/${total}` : undefined };
    }

    case "titleRendered": {
      const titles: TitleAsset[] = titlesQ.data?.titles ?? [];
      return { done: titles.some((t) => t.exists || t.status === "rendered") };
    }

    case "shotRendered": {
      const shots: Shot[] = shotsQ.data?.shots ?? [];
      return { done: shots.some((s) => s.webp_exists || s.status === "rendered") };
    }

    case "finalExists": {
      const final = finalQ.data as FinalInfo | undefined;
      if (run?.running) return { done: false, detail: "rendering…" };
      return { done: !!final?.exists };
    }

    default:
      return { done: false };
  }
}
