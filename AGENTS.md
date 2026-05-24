# Dicta Project Codex Rules

Common Codex rules live in `C:\Users\Olga\.codex\AGENTS.md`. Do not duplicate them in this project file.

- Working folder: `C:\Users\Olga\Documents\VoiceHelper`.
- The product name is Dicta; the repository folder may still be named `VoiceHelper`.
- Main GUI source: `dicta.py`.
- Packaged executable for manual verification: `C:\Users\Olga\Documents\VoiceHelper\dist\Dicta\Dicta.exe`.
- Do not commit or push unless the user explicitly asks.
- Before code, packaging, or documentation changes, check `git status --short` and the relevant diff.
- Preserve the local package layout: `models`, `.tools`, `assets`, `docs`, and `scripts` must stay next to `Dicta.exe` in the packaged folder.
- Use `scripts\build_dicta_exe.ps1` for package rebuilds. Keep long build/test output in `artifacts` and summarize only the result, failures, and artifact paths.
- When providing a clickable link to `Dicta.exe`, also include current context-fill information and a recommendation on whether to continue in the current chat or move to a new chat.
- Dicta-specific continuity files live in `docs\codex-handoff.md`, `docs\plans.md`, and `docs\decision-log.md`.
- Do not use similarly named files from `C:\Users\Olga\Documents\Codex\...`, `C:\Users\Olga\Documents\AKB5`, or other projects as source of truth for Dicta.
