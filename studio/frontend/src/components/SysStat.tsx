import { useQuery } from "@tanstack/react-query";

interface Stat {
  cpu_pct: number | null;
  gpu_pct: number | null;
  gpu_mem_used_mib: number | null;
  gpu_mem_total_mib: number | null;
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
// red when hot, faint otherwise — quick glanceable load signal
const hot = (v: number | null | undefined) =>
  v != null && v >= 90 ? { color: "var(--red)" } : undefined;

/* Live-ish host readout (CPU / GPU / GPU RAM) for the topbar. Polls every 2s. */
export function SysStat() {
  const q = useQuery<Stat>({
    queryKey: ["sysstat"],
    queryFn: () => fetch("/api/sysstat").then((r) => r.json()),
    refetchInterval: 2000,
    staleTime: 0,
  });
  const s = q.data;
  const mem =
    s?.gpu_mem_used_mib != null && s?.gpu_mem_total_mib != null
      ? `${(s.gpu_mem_used_mib / 1024).toFixed(1)}/${(s.gpu_mem_total_mib / 1024).toFixed(1)}G`
      : "—";
  return (
    <div className="flex items-center gap-2" title="host CPU · GPU · GPU RAM (updates ~2s)">
      <span className="seg-readout">
        CPU <span style={hot(s?.cpu_pct)}>{pct(s?.cpu_pct)}</span>
      </span>
      <span className="seg-readout cyan">
        GPU <span style={hot(s?.gpu_pct)}>{pct(s?.gpu_pct)}</span>
        <span className="text-txt-faint"> · {mem}</span>
      </span>
    </div>
  );
}
