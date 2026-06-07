# Contributing

Thanks for your interest in MACU Studio. This is a small, self-hosted project — issues
and pull requests are welcome.

## Ground rules

- **License.** By contributing you agree your changes are licensed under the project's
  [Apache-2.0 license](LICENSE).
- **No content in PRs.** This repo ships the engine, not anyone's shows. Don't add
  episodes, per-show canon, cloned voices, or other creative content — those live in
  the gitignored `episode_meta/` (a separate content repo, see the git-sync section in
  [INSTALL.md](INSTALL.md)) and `docs/shows/<id>/`.
- **No secrets / no machine-specific values.** Keep paths and endpoints env-driven
  (`config.py` / `pipeline/lib.py` read a repo-root `.env`; defaults must work
  unconfigured). Never commit a `.env`, a token, a LAN IP, or a personal absolute path.

## Layout

- `pipeline/` — the 8-stage render pipeline + `serve.py` (the `:8773` render service).
- `studio/backend/macu_studio/` — the FastAPI app; `studio/frontend/` — the React SPA.
- `deploy/` — installer, service compose stacks, systemd templates, the chat bridge.
- `docs/_common/` + `docs/_templates/show/` — shared docs + new-show scaffolding.

## Before opening a PR

The CI (`.github/workflows/ci.yml`) runs these — please run them locally first:

```bash
python -m compileall pipeline studio/backend/macu_studio   # byte-compile
pip install ./studio && python -c "import macu_studio.main" # backend imports
cd studio/frontend && npm ci && npm run build               # tsc + vite build
```

Keep changes focused, match the surrounding style, and explain the "why" in the PR
description. For anything that touches the render path or the installer, note how you
verified it (a fresh-machine path is the easy thing to break).
