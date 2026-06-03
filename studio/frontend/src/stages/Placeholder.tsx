export function Placeholder({ stage, slug }: { stage: string; slug: string }) {
  return (
    <div className="panel p-6 h-full grid place-items-center text-center">
      <div>
        <div className="panel-title mb-2">Stage: {stage}</div>
        <p className="text-txt-dim">
          Coming soon. v0.1 ships Stage 5 (Assembly) end-to-end. Other stages will land in subsequent versions.
        </p>
        <p className="text-txt-faint mt-3 label-tiny">episode {slug}</p>
      </div>
    </div>
  );
}
