import { useQuery } from "@tanstack/react-query";

interface Stat {
  cpu_pct: number | null;
  gpu_pct: number | null;
  gpu_mem_used_mib: number | null;
  gpu_mem_total_mib: number | null;
  disk_read_mibps: number | null;
  disk_write_mibps: number | null;
  disk_busy_pct: number | null;
  disk_dev: string | null;
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
// red when hot, faint otherwise — quick glanceable load signal
const hot = (v: number | null | undefined) =>
  v != null && v >= 90 ? { color: "var(--red)" } : undefined;
// green when the storage drive is reading hard — a model is loading into VRAM
const reading = (v: number | null | undefined) =>
  v != null && v >= 50 ? { color: "var(--green)" } : undefined;
const mbps = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}`);

/* Live-ish host readout (CPU / GPU / GPU RAM / storage-disk I/O) for the topbar. Polls every 2s. */
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
    <div className="flex items-center gap-2" title="host CPU · GPU · GPU RAM · storage disk I/O (updates ~2s)">
      <span className="seg-readout">
        CPU <span style={hot(s?.cpu_pct)}>{pct(s?.cpu_pct)}</span>
      </span>
      <span className="seg-readout cyan">
        GPU <span style={hot(s?.gpu_pct)}>{pct(s?.gpu_pct)}</span>
        <span className="text-txt-faint"> · </span><span className="text-amber">{mem}</span>
      </span>
      <span className="seg-readout" title={`storage drive (${s?.disk_dev ?? "?"}) read↓ / write↑ MB/s`}>
        DSK <span style={reading(s?.disk_read_mibps)}>{mbps(s?.disk_read_mibps)}↓</span>
        <span className="text-txt-faint"> {mbps(s?.disk_write_mibps)}↑ MB/s</span>
      </span>
    </div>
  );
}
