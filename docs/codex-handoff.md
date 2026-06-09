# Dicta Codex Handoff

Last updated: 2026-06-08

Workspace: `C:\Users\Olga\Documents\VoiceHelper`

Packaged app for DictaProtocol manual checks: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`

## Current State

- Current branch: `DictaProtocol`, tracking `origin/DictaProtocol`.
- HEAD and latest pushed commit: `ccfab8f Complete protocol stitching and draft output`.
- Current working tree has uncommitted implemented stage 3.5 UI work after `ccfab8f`; do not overwrite it.
- Uncommitted code work: `dicta.py` adds compact long-recording protocol progress status, processed-fragment counting, clear `Запись` / `Обработка фрагмента` / `Протокол готов` states, adaptive lower-bar layout that moves the protocol status to a second row in narrow windows, simplified spelling context menu with one user-facing action for accepted words, real clock time in visible protocol fragment headers, text-level filtering of long same-fragment system-audio repeats from microphone blocks, and `[неразборчиво]` marking for protocol sentences with dense invalid-word clusters.
- Uncommitted docs work: `docs\plans.md`, `docs\codex-handoff.md`, and `docs\decision-log.md` describe stage 3.5 status UI work and stage 3.6 verification results.
- Do not commit or push unless the user explicitly asks.

## Build And Package

- Build DictaProtocol manual-check package with:

```powershell
.\scripts\build_dicta_exe.ps1 -PackageVersion "1.1-pilot-protocol" -DistRoot "dist\DictaProtocol"
```

- `-DistRoot` defaults to `dist\Dicta`, but DictaProtocol manual checks must use `dist\DictaProtocol`.
- Current packaged EXE: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.
- In user-facing final responses, report the ready EXE as a clickable Markdown file link to the absolute path.
- Current packaged EXE timestamp observed locally: 2026-06-08 21:35:48.
- Latest build log observed locally: `artifacts\build_protocol_option_b_20260608_213514.log`.
- Latest build log result: package verification passed.

## Validation Already Run

- `python -m py_compile dicta.py`
- `python dicta.py --format-test`
- `python dicta.py --postprocess-test`
- `python dicta.py --dictionary-test`
- `python dicta.py --self-test --allow-missing-models`
- `.\scripts\build_dicta_exe.ps1 -PackageVersion "1.1-pilot-protocol" -DistRoot "dist\DictaProtocol"`; output captured in `artifacts\build_protocol_option_b_20260608_213514.log`.
- `dist\DictaProtocol\Dicta.exe --format-test`
- `dist\DictaProtocol\Dicta.exe --postprocess-test`
- `dist\DictaProtocol\Dicta.exe --self-test --allow-missing-models`
- `.\scripts\verify_dicta_package.ps1 -Root .\dist\DictaProtocol`; output captured in `artifacts\stage_3_6_verify_package_20260608_180218.log`.
- `.\dist\DictaProtocol\scripts\diagnose_dicta.ps1 -SkipNetworkAudit`; output captured in `artifacts\stage_3_6_packaged_diagnose_20260608_182758.log`; report saved in `dist\DictaProtocol\diagnostics\dicta_diagnostic_20260608_182758.txt`.
- Packaged audio-device listing captured in `artifacts\stage_3_6_packaged_audio_devices_20260608_180902.log`.
- GUI single-instance and idle mini-panel smoke captured in `artifacts\stage_3_6_gui_check_20260608_181101.json` and `artifacts\stage_3_6_gui_minimized_20260608_181101.png`.
- GUI mini-panel record/stop smoke captured in `artifacts\stage_3_6_mini_record_stop_20260608_182528.json` and `artifacts\stage_3_6_mini_record_panel_before_stop_20260608_182528.png`.

## Active Plan

- Stage 2 is closed by manual verification.
- Stage 3.1 is implemented and accepted: protocol output separates system sound and microphone blocks.
- Stage 3.2 is implemented, manually checked, committed, and pushed: fragment time ranges, protocol diagnostics, and microphone duplicate filtering.
- Stage 3.2.1 is implemented, built, committed, and pushed: Russian abbreviation normalization with a general Latin-CAPS-to-Cyrillic rule and a stop-list.
- Stage 3.3 is implemented, built, committed, and pushed: conservative chunk stitching removes obvious repeated text at fragment boundaries per source.
- Stage 3.4 is implemented, built, committed, and pushed: protocol output is formatted as `Черновик протокола` with neutral fragment headers.
- Stage 3.5 was committed and pushed in `d5ba167`: long-recording UI with fragment progress, clear recording/processing/ready states, readable protocol status in narrow windows, visible protocol fragment headers by real system time, reduced microphone/system duplicate text in the same fragment, and conservative `[неразборчиво]` marking for obvious recognition garbage.
- Stage 3.6 automated/package verification was committed and pushed in `d5ba167`. Source and packaged quick tests passed, package verification passed, packaged diagnostic completed with zero blocking failures, second-instance restore passed, minimize-to-tray mini-panel passed, and a short silent recording could be stopped from the mini-panel.
- Stage 3.6 is not fully closed until real audio manual checks are run: microphone-only speech, system-audio-only playback, combined system audio plus microphone, 3-5 minute recording, and one-source-silent recording.
- Stage 3.6 warnings to keep visible: microphone diagnostics opened devices but measured 0% peak, packaged diagnostic reported no Dicta firewall rule, `%TEMP%` has Dicta temporary leftovers, and network audit was skipped by parameter.
- Stage 4 source-separation quality implementation is complete through 4.3: 4.1 diagnostics, 4.2 delayed leakage handling, and 4.3 hiding/cleaning leaked microphone blocks are implemented in code and packaged in `dist\DictaProtocol`; 4.4 manual source-quality regression is still pending.
- Stage 4 initial build log: `artifacts\build_protocol_stage4_20260608_221444.log`. Package verification passed; packaged `--format-test`, `--postprocess-test`, `--dictionary-test`, and `--self-test --allow-missing-models` returned exit code 0.
- After analyzing `dist\DictaProtocol\artifacts\protocol_diagnostics_20260608_224905`, extra 4.3 cleanup was added: do not glue text before and after a removed system duplicate, drop obvious lowercase tails, drop short connector prefixes after a system duplicate, keep first-person microphone remarks, and log `removed_middle`, `dropped_prefix`, `dropped_tail`, `kept_microphone`.
- Source validation after that refinement passed: `python -m py_compile dicta.py`, `python dicta.py --format-test`, `python dicta.py --postprocess-test`, `python dicta.py --dictionary-test`, and `python dicta.py --self-test --allow-missing-models`.
- Refined stage 4 package was rebuilt after the app was closed: `artifacts\build_protocol_stage4_refine_20260609_070901.log`. Package verification passed; packaged `--format-test`, `--postprocess-test`, `--dictionary-test`, and `--self-test --allow-missing-models` returned exit code 0. Ready EXE: `dist\DictaProtocol\Dicta.exe`.

## Long Command Visibility Rule

- For build/package/self-test commands that may take more than 30 seconds, send one short update before the command with expected duration and the next step.
- Run the command with a finite timeout.
- After the command returns, send one short update with actual elapsed time and result before starting another long step.
- If the user interrupts during a perceived hang, check live processes first and report the exact process/build state.

## Next Action

- Next required work: manual-check 4.4 with real combined recordings from the rebuilt `dist\DictaProtocol\Dicta.exe`.
