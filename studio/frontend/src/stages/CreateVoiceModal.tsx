import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { voicesApi, type CreatedVoice } from "../api/voices";
import { useStore } from "../store";
import { Modal } from "../components/Modal";
import { useT } from "../i18n";

/** Upload a reference clip (mp3/wav/m4a/mp4) → clone it as an OmniVoice profile.
 * The backend starts the OmniVoice container on demand (consumer-lifecycle), so
 * the first clone of a session can take up to ~3 min to warm the GPU. */
export function CreateVoiceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

  const [name, setName] = useState("");
  const [language, setLanguage] = useState("English");
  const [testText, setTestText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<"form" | "working" | "done">("form");
  const [err, setErr] = useState("");
  const [result, setResult] = useState<CreatedVoice | null>(null);

  const reset = () => {
    setName(""); setLanguage("English"); setTestText(""); setFile(null);
    setPhase("form"); setErr(""); setResult(null);
  };
  const close = () => { if (phase === "working") return; reset(); onClose(); };

  const submit = async () => {
    if (!name.trim()) { setErr(t("createvoice.errNameRequired")); return; }
    if (!file) { setErr(t("createvoice.errFileRequired")); return; }
    setErr(""); setPhase("working");
    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("language", language.trim() || "English");
      if (testText.trim()) form.append("test_text", testText.trim());
      form.append("file", file);
      const r = await voicesApi.create(form);
      setResult(r); setPhase("done");
      push(t("toast.voiceCloned", { name: r.name }), "ok");
      qc.invalidateQueries({ queryKey: ["voices"] });
    } catch (e) {
      setErr((e as Error).message); setPhase("form");
    }
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={t("createvoice.title")}
      width={560}
      footer={
        phase === "done" ? (
          <button className="btn btn-amber" onClick={close}>{t("common.close")}</button>
        ) : (
          <>
            <button className="btn" onClick={close} disabled={phase === "working"}>{t("common.cancel")}</button>
            <button className="btn btn-amber" onClick={submit} disabled={phase === "working"}>
              {phase === "working" ? t("createvoice.cloning") : t("createvoice.cloneVoice")}
            </button>
          </>
        )
      }
    >
      {phase !== "done" ? (
        <div className="flex flex-col gap-3 p-3 text-[13px]">
          <label className="flex flex-col gap-1">
            <span className="label-tiny">{t("createvoice.labelVoiceName")} <span className="text-txt-faint">{t("createvoice.hintVoiceName")}</span></span>
            <input className="input py-1.5" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("createvoice.placeholderVoiceName")} />
          </label>

          <label className="flex flex-col gap-1">
            <span className="label-tiny">{t("createvoice.labelRefClip")} <span className="text-txt-faint">{t("createvoice.hintRefClip")}</span></span>
            <input
              type="file"
              accept="audio/*,video/mp4,.mp3,.wav,.m4a,.mp4,.aac,.ogg,.flac"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-[12px]"
            />
            {file && <span className="label-tiny text-txt-faint">{t("createvoice.fileInfo", { fileName: file.name, size: (file.size / 1024 / 1024).toFixed(1) })}</span>}
          </label>

          <label className="flex flex-col gap-1 w-1/2">
            <span className="label-tiny">{t("createvoice.labelLanguage")}</span>
            <input className="input py-1.5" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </label>

          <label className="flex flex-col gap-1">
            <span className="label-tiny">{t("createvoice.labelTestLine")} <span className="text-txt-faint">{t("createvoice.hintTestLine")}</span></span>
            <textarea className="input text-[12px]" rows={2} value={testText} onChange={(e) => setTestText(e.target.value)} placeholder={t("createvoice.placeholderTestLine")} />
          </label>

          {phase === "working" && (
            <div className="text-amber text-[12px]">{t("createvoice.workingMsg")}</div>
          )}
          {err && <div className="text-red text-[12px]">{err}</div>}
          <div className="label-tiny text-txt-faint">{t("createvoice.footerNote")}</div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 p-3 text-[13px]">
          <div className="text-green">{t("createvoice.doneLine", { name: result?.name })}</div>
          <div className="label-tiny text-txt-faint">{t("createvoice.labelProfileId")} <span className="font-mono">{result?.id}</span></div>
          {result?.test_file && (
            <div className="flex flex-col gap-1">
              <span className="label-tiny">{t("createvoice.labelTestSample")}</span>
              <audio controls src={voicesApi.sampleUrl(result.test_file)} className="w-full" />
            </div>
          )}
          <div className="label-tiny text-txt-faint">{t("createvoice.doneFooterNote")}</div>
        </div>
      )}
    </Modal>
  );
}
