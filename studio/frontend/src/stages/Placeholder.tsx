import { useT } from "../i18n";

export function Placeholder({ stage, slug }: { stage: string; slug: string }) {
  const t = useT();
  return (
    <div className="panel p-6 h-full grid place-items-center text-center">
      <div>
        <div className="panel-title mb-2">{t("placeholder.stageTitle", { stage })}</div>
        <p className="text-txt-dim">
          {t("placeholder.comingSoon")}
        </p>
        <p className="text-txt-faint mt-3 label-tiny">{t("placeholder.episodeLabel", { slug })}</p>
      </div>
    </div>
  );
}
