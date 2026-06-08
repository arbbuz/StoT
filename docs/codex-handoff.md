# Dicta Codex Handoff

Last updated: 2026-06-08

Workspace: `C:\Users\Olga\Documents\VoiceHelper`

Packaged app for DictaProtocol manual checks: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`

## Current State

- Current branch: `DictaProtocol`, tracking `origin/DictaProtocol`.
- HEAD and latest pushed commit: `a055042 Improve mini panel controls and abbreviation normalization`.
- Current working tree has uncommitted work after `a055042`; do not overwrite it.
- Uncommitted code work: `dicta.py` contains stage 3.3 protocol chunk stitching, repeated-tail removal, and stage 3.4 draft protocol formatting.
- Uncommitted build work: `scripts\build_dicta_exe.ps1` adds `-DistRoot`, stages PyInstaller output under `build\pyinstaller-dist`, and repopulates only the selected package folder under `dist`.
- Uncommitted docs work: `docs\plans.md`, `docs\decision-log.md`, and `docs\UPDATE_PROCEDURE.md` describe stage 3.3, stage 3.4, restored stage 3.5/3.6 planning, and `-DistRoot`.
- Do not commit or push unless the user explicitly asks.

## Build And Package

- Build DictaProtocol manual-check package with:

```powershell
.\scripts\build_dicta_exe.ps1 -PackageVersion "1.1-pilot-protocol" -DistRoot "dist\DictaProtocol"
```

- `-DistRoot` defaults to `dist\Dicta`, but DictaProtocol manual checks must use `dist\DictaProtocol`.
- Current packaged EXE: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.
- In user-facing final responses, report the ready EXE as a clickable Markdown file link to the absolute path.
- Current packaged EXE timestamp observed locally: 2026-06-08 07:21:46.
- Latest build log observed locally: `artifacts\build_protocol_draft_stage_3_4_20260608_072106.log`.
- Latest build log result: package verification passed.

## Validation Already Run

- `python -m py_compile dicta.py`
- `python dicta.py --format-test`
- `python dicta.py --postprocess-test`
- `.\scripts\build_dicta_exe.ps1 -PackageVersion "1.1-pilot-protocol" -DistRoot "dist\DictaProtocol"`; output captured in `artifacts\build_protocol_draft_stage_3_4_20260608_072106.log`.
- `dist\DictaProtocol\Dicta.exe --format-test`
- `dist\DictaProtocol\Dicta.exe --postprocess-test`

## Active Plan

- Stage 2 is closed by manual verification.
- Stage 3.1 is implemented and accepted: protocol output separates system sound and microphone blocks.
- Stage 3.2 is implemented, manually checked, committed, and pushed: fragment time ranges, protocol diagnostics, and microphone duplicate filtering.
- Stage 3.2.1 is implemented, built, committed, and pushed: Russian abbreviation normalization with a general Latin-CAPS-to-Cyrillic rule and a stop-list.
- Stage 3.3 is implemented in the current uncommitted working tree and fresh packaged build: conservative chunk stitching removes obvious repeated text at fragment boundaries per source.
- Stage 3.4 is implemented in the current uncommitted working tree and fresh packaged build: protocol output is formatted as `Черновик протокола` with neutral fragment headers.
- Stage 3.5 is the next planned work: long-recording UI with fragment progress and clear recording/processing/ready states.
- Stage 3.6 is planned after 3.5: reliability and manual verification for the full stage 3 flow.

## Long Command Visibility Rule

- For build/package/self-test commands that may take more than 30 seconds, send one short update before the command with expected duration and the next step.
- Run the command with a finite timeout.
- After the command returns, send one short update with actual elapsed time and result before starting another long step.
- If the user interrupts during a perceived hang, check live processes first and report the exact process/build state.

## Next Action

- If the user asks to finish the current work, review the uncommitted changes, run the quick tests again, and commit/push only with explicit permission.
- If the user asks to continue stage 3, start with stage 3.5 long-recording UI.
