# Dicta Codex Handoff

Last updated: 2026-06-04

Workspace: `C:\Users\Olga\Documents\VoiceHelper`

Packaged app for DictaProtocol manual checks: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`

## Current DictaProtocol Handoff

- Current branch: `DictaProtocol`, tracking `origin/DictaProtocol`.
- Last pushed commit before the current uncommitted work: `71df883 Refine Dicta protocol audio and backend selection`.
- Current uncommitted work is in `dicta.py`: stage 2 meeting protocol capture, toolbar source selector, and long-meeting streaming protocol changes.
- Current packaged EXE for manual verification: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.
- Do not create additional folders under `dist`; keep using only existing `dist\DictaProtocol` for this branch unless the user explicitly asks otherwise.
- Do not commit or push unless the user explicitly asks.

## Long Command Visibility Rule

- For build/package/self-test commands that may take more than 30 seconds, do not split the work into many tiny commands just to show activity.
- Before the long command, send one short update with expected duration and the exact next step after it.
- Run the command with a finite timeout.
- Immediately after the command returns, send one short update with actual elapsed time and result before starting another long step.
- Do not say that the process is normal/fine unless the command has returned successfully.
- If the user interrupts during a perceived hang, first check live processes and report the exact process/build state.

## Current State

- Project name: Dicta.
- Repository folder is still `VoiceHelper`.
- Current branch: `main`, tracking `origin/main`.
- Last pushed commit known before the current uncommitted work: `bb26547 Make app icon corners transparent`.
- Do not commit or push without explicit user permission.
- Global Codex rules are stored in `C:\Users\Olga\.codex\AGENTS.md`; this project should keep only Dicta-specific rules in `AGENTS.md`.
- Fresh packaged EXE for manual verification was rebuilt on 2026-05-26 20:48:26 at `C:\Users\Olga\Documents\VoiceHelper\dist\Dicta\Dicta.exe`.

## Current Uncommitted Work

- `dicta.py`: added resilient microphone opening, grouped input fallback, samplerate fallback, 1 -> 2 channel fallback with mono downmix, background "Найти микрофон" UI, and `--microphone-diagnostics`.
- Follow-up fix: input modes are now accepted only after `RawInputStream.start()` succeeds, and "Найти микрофон" no longer switches selection to a silent fallback device.
- Follow-up fix: "Проверить" now runs the same mode probing for the selected microphone, shows progress, and stores the successful mode for the next recording.
- Follow-up fix: USB PnP microphones now try `RawInputStream` formats in order: `int16`, `float32`, `int24`, `int32`; non-PCM16 input is converted to PCM16 mono inside Dicta before level/VAD/Whisper. Microphone diagnostics now prints all failed mode attempts, not only the tail.
- Follow-up fix: quiet PCM16 audio can be manually amplified inside Dicta before VAD/Whisper; the settings window has a "Усиление записи" percent slider that defaults to no gain, and recognition status shows percent/multiplier plus peak before/after when gain is applied.
- Follow-up UI fix: the search progressbar is cleared when "Проверить" starts/finishes and when microphone search completes, so it does not look like a stuck level meter.
- Follow-up UI fix: the settings-tab bar is now bound to the actual microphone level, not to internal search progress.
- Follow-up UI fix: recording settings controls no longer shift when microphone test status or manual gain text changes; microphone action buttons are grouped in a stable row and dynamic labels use fixed widths.
- Follow-up UI fix: the settings window is centered over the main Dicta window each time it opens.
- Follow-up settings UI: added "Сохранить" and "Отмена" buttons in the settings window; they save or restore settings, then close the window.
- `docs\STAGE_0_2_1_MICROPHONE.md`: updated for selected-device mode probing and manual audio gain status.
- `scripts\diagnose_dicta.ps1`: added "Microphone quick open test" and redirected windowed `Dicta.exe` stdout/stderr through `Start-Process`.
- `docs\USER_CHECKLIST.md`, `docs\STAGE_0_2_1_MICROPHONE.md`, `docs\STAGE_0_2_2_DIAGNOSTICS.md`: updated for microphone search and diagnostics.
- `AGENTS.md`, `docs\codex-handoff.md`, `docs\plans.md`, `docs\decision-log.md`: split global/project Codex rules and created Dicta-specific continuity docs.
- Other uncommitted packaging/docs/model-selection changes are present in the working tree; preserve them unless the current task explicitly asks otherwise.

## Verification Already Run

- `python -m py_compile dicta.py windows_spellcheck.py`
- `python dicta.py --self-test --allow-missing-models`
- `python dicta.py --audio-devices`
- `python dicta.py --microphone-diagnostics --seconds 0.2`
- `scripts\build_dicta_exe.ps1`
- `dist\Dicta\Dicta.exe --audio-devices`
- `dist\Dicta\Dicta.exe --microphone-diagnostics --seconds 0.2` with stdout redirection
- `dist\Dicta\scripts\diagnose_dicta.ps1 -Root .\dist\Dicta -SkipNetworkAudit`
- `python -m py_compile dicta.py`
- Direct function check for `apply_pcm16_gain`
- `python dicta.py --format-test`
- `git diff --check -- dicta.py docs/STAGE_0_2_1_MICROPHONE.md` with CRLF warnings only
- `scripts\build_dicta_exe.ps1` on 2026-05-26 with build output captured in `artifacts\build_dicta_exe_20260526_204800.log`
- `dist\Dicta\Dicta.exe --self-test --allow-missing-models`

Latest successful build log:

- `artifacts\build_dicta_exe_20260526_204800.log`

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
6. For a quiet recording, first keep "Усиление записи" at `0%` and verify there is no software gain, then set a manual percent and verify that the status shows `усиление +N% (xM), пик A->B%`.
7. If a USB headset fails, run `dist\Dicta\scripts\diagnose_dicta.cmd` and inspect the generated report in `dist\Dicta\diagnostics`.
