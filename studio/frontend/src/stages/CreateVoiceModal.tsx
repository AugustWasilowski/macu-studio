import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { voicesApi, type CreatedVoice } from "../api/voices";
import { useStore } from "../store";
import { Modal } from "../components/Modal";

/** Upload a reference clip (mp3/wav/m4a/mp4) → clone it as an OmniVoice profile.
 * The backend starts the OmniVoice container on demand (consumer-lifecycle), so
 * the first clone of a session can take up to ~3 min to warm the GPU. */
export function CreateVoiceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
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
    if (!name.trim()) { setErr("Voice name is required."); return; }
    if (!file) { setErr("Choose a reference clip."); return; }
    setErr(""); setPhase("working");
    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("language", language.trim() || "English");
      if (testText.trim()) form.append("test_text", testText.trim());
      form.append("file", file);
      const r = await voicesApi.create(form);
      setResult(r); setPhase("done");
      push(`Voice "${r.name}" cloned`, "ok");
      qc.invalidateQueries({ queryKey: ["voices"] });
    } catch (e) {
      setErr((e as Error).message); setPhase("form");
    }
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title="CREATE VOICE"
      width={560}
      footer={
        phase === "done" ? (
          <button className="btn btn-amber" onClick={close}>Done</button>
        ) : (
          <>
            <button className="btn" onClick={close} disabled={phase === "working"}>Cancel</button>
            <button className="btn btn-amber" onClick={submit} disabled={phase === "working"}>
              {phase === "working" ? "Cloning…" : "Clone voice"}
            </button>
          </>
        )
      }
    >
      {phase !== "done" ? (
        <div className="flex flex-col gap-3 p-3 text-[13px]">
          <label className="flex flex-col gap-1">
            <span className="label-tiny">Voice name <span className="text-txt-faint">(e.g. Vivian — becomes the OmniVoice profile name)</span></span>
            <input className="input py-1.5" value={name} onChange={(e) => setName(e.target.value)} placeholder="Vivian" />
          </label>

          <label className="flex flex-col gap-1">
            <span className="label-tiny">Reference clip <span className="text-txt-faint">(mp3 / wav / m4a / mp4 — a few clean seconds of the target voice)</span></span>
            <input
              type="file"
              accept="audio/*,video/mp4,.mp3,.wav,.m4a,.mp4,.aac,.ogg,.flac"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-[12px]"
            />
            {file && <span className="label-tiny text-txt-faint">{file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB</span>}
          </label>

          <label className="flex flex-col gap-1 w-1/2">
            <span className="label-tiny">Language</span>
            <input className="input py-1.5" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </label>

          <label className="flex flex-col gap-1">
            <span className="label-tiny">Test line <span className="text-txt-faint">(optional — generates a sample so you can hear the clone)</span></span>
            <textarea className="input text-[12px]" rows={2} value={testText} onChange={(e) => setTestText(e.target.value)} placeholder="Leave blank for a default test line." />
          </label>

          {phase === "working" && (
            <div className="text-amber text-[12px]">Starting OmniVoice (first clone of the session can take up to ~3 min to warm the GPU) and cloning… keep this open.</div>
          )}
          {err && <div className="text-red text-[12px]">{err}</div>}
          <div className="label-tiny text-txt-faint">Clones via OmniVoice on the 2080 Ti. The clip is auto-normalized to 24kHz mono. A same-named voice is replaced.</div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 p-3 text-[13px]">
          <div className="text-green">✓ Cloned <b>{result?.name}</b></div>
          <div className="label-tiny text-txt-faint">profile id: <span className="font-mono">{result?.id}</span></div>
          {result?.test_file && (
            <div className="flex flex-col gap-1">
              <span className="label-tiny">Test sample</span>
              <audio controls src={voicesApi.sampleUrl(result.test_file)} className="w-full" />
            </div>
          )}
          <div className="label-tiny text-txt-faint">Add it to a character in this show's Voice Roster / the manifest to use it for VO.</div>
        </div>
      )}
    </Modal>
  );
}
