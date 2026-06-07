// Product / technical terms that must NEVER be translated. The translation pipeline
// asserts each of these survives verbatim in every locale; the runtime doesn't use
// this list, but it's kept here as the single source of truth shared with the
// haiku-worker prompts (scripts/i18n-translate.mjs).
export const GLOSSARY: string[] = [
  "MACU",
  "MACU Studio",
  "ComfyUI",
  "OmniVoice",
  "Ollama",
  "Piper",
  "ttyd",
  "tmux",
  "GPU",
  "VRAM",
  "git",
  "slug",
  "VO",
  "SFX",
  "RIFE",
  "zeroscope",
  "faster-whisper",
  "SRT",
  "systemd",
  "Claude",
  "Claude Code",
  "YouTube",
  "JSON",
  "Markdown",
  "b-roll",
  "HyperFrames",
];
