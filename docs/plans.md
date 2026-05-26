# Dicta Plans

Last updated: 2026-05-26

This file is the Dicta-specific project plan. Global Codex operating rules belong in `C:\Users\Olga\.codex\AGENTS.md`.

## Active Plan

1. USB headset resilience
   - Status: implemented in code and fresh packaged build.
   - Remaining: manual verification with the target USB headset.
   - Success signal: "Найти микрофон" selects a working input, including `float32`, `int24`, or `int32` fallback mode if needed, "Проверить" shows a moving level, and a short recording is recognized.

2. Diagnostics quality
   - Status: `--microphone-diagnostics` and "Microphone quick open test" are implemented.
   - Remaining: collect a real report from a failing USB headset if the issue reproduces.
   - Success signal: the report shows grouped devices, exact open mode, peak level, and the failing backend/rate/channel combinations.

3. Quiet microphone manual gain
   - Status: implemented in code and fresh packaged build.
   - Remaining: manual verification with a quiet microphone recording.
   - Success signal: at `0%` Dicta does not alter good recordings; after choosing a manual percent, recognition still works and the status shows `усиление +N% (xM), пик A->B%`.

4. Package readiness
   - Status: `scripts\build_dicta_exe.ps1` builds `dist\Dicta` successfully; latest fresh EXE is dated 2026-05-26 20:35:35.
   - Remaining: repeat package verification after manual headset testing if any code changes are made.
   - Success signal: `verify_dicta_package.ps1`, `Dicta.exe --self-test`, and the microphone diagnostic pass with no blocking failures.

5. Commit/push decision
   - Status: pending user approval.
   - Remaining: review final diff, then commit only if explicitly requested.

## Maintenance Notes

- Keep Dicta plans here, not in archived workspaces under `C:\Users\Olga\Documents\Codex\...`.
- Keep long verification output in `artifacts`.
- Keep user-facing procedure updates in `docs\USER_CHECKLIST.md`.
- Keep architecture and behavioral decisions in `docs\decision-log.md`.
