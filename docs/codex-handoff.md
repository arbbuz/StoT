# Dicta Codex Handoff

Last updated: 2026-05-24

Workspace: `C:\Users\Olga\Documents\VoiceHelper`

Packaged app: `C:\Users\Olga\Documents\VoiceHelper\dist\Dicta\Dicta.exe`

## Current State

- Project name: Dicta.
- Repository folder is still `VoiceHelper`.
- Last pushed commit known before the current uncommitted work: `bb26547 Make app icon corners transparent`.
- Do not commit or push without explicit user permission.
- Global Codex rules are stored in `C:\Users\Olga\.codex\AGENTS.md`; this project should keep only Dicta-specific rules in `AGENTS.md`.

## Current Uncommitted Work

- `dicta.py`: added resilient microphone opening, grouped input fallback, samplerate fallback, 1 -> 2 channel fallback with mono downmix, background "Найти микрофон" UI, and `--microphone-diagnostics`.
- Follow-up fix: input modes are now accepted only after `RawInputStream.start()` succeeds, and "Найти микрофон" no longer switches selection to a silent fallback device.
- Follow-up UI fix: the search progressbar is cleared when "Проверить" starts/finishes and when microphone search completes, so it does not look like a stuck level meter.
- Follow-up UI fix: the settings-tab bar is now bound to the actual microphone level, not to internal search progress.
- Follow-up settings UI: added "Сохранить" and "Отмена" buttons in the settings window; they save or restore settings without closing the window.
- `scripts\diagnose_dicta.ps1`: added "Microphone quick open test" and redirected windowed `Dicta.exe` stdout/stderr through `Start-Process`.
- `docs\USER_CHECKLIST.md`, `docs\STAGE_0_2_1_MICROPHONE.md`, `docs\STAGE_0_2_2_DIAGNOSTICS.md`: updated for microphone search and diagnostics.
- `AGENTS.md`, `docs\codex-handoff.md`, `docs\plans.md`, `docs\decision-log.md`: split global/project Codex rules and created Dicta-specific continuity docs.

## Verification Already Run

- `python -m py_compile dicta.py windows_spellcheck.py`
- `python dicta.py --self-test --allow-missing-models`
- `python dicta.py --audio-devices`
- `python dicta.py --microphone-diagnostics --seconds 0.2`
- `scripts\build_dicta_exe.ps1`
- `dist\Dicta\Dicta.exe --audio-devices`
- `dist\Dicta\Dicta.exe --microphone-diagnostics --seconds 0.2` with stdout redirection
- `dist\Dicta\scripts\diagnose_dicta.ps1 -Root .\dist\Dicta -SkipNetworkAudit`

Latest successful build log:

- `artifacts\build_dicta_20260524_124454.stdout.log`
- `artifacts\build_dicta_20260524_124454.stderr.log`

Latest successful dist diagnostic log:

- `artifacts\diagnose_dist_20260524_120436.log`

Known diagnostic warnings:

- Firewall block rule was not found on this machine.
- Network audit was skipped in the verification run.

## Next Manual Check

1. Open `dist\Dicta\Dicta.exe`.
2. Go to "Настройки" -> "Запись".
3. Click "Найти микрофон" while speaking into the target USB headset.
4. Click "Проверить" on the selected microphone.
5. Make a short recording and verify that recognition still works.
6. If a USB headset fails, run `dist\Dicta\scripts\diagnose_dicta.cmd` and inspect the generated report in `dist\Dicta\diagnostics`.
