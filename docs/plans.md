# Dicta Plans

Last updated: 2026-06-08

This file is the Dicta-specific project plan. Global Codex operating rules belong in `C:\Users\Olga\.codex\AGENTS.md`.

## Current Branch

- Branch: `DictaProtocol`.
- Packaged EXE for manual checks: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.
- Latest pushed protocol commit: `ccfab8f Complete protocol stitching and draft output`.
- Current local work after that commit contains implemented stage 3.5 long-recording UI and a fresh packaged build; commit/push is still pending.
- Do not commit or push unless the user explicitly asks.

## Active Plan

1. Stage 2: combined meeting recording
   - Status: closed by manual verification.
   - Implemented: recording from system audio and microphone in one session, tray mini-panel, single-instance behavior, protocol recording flow.
   - Success signal: Dicta records both Windows/system sound and microphone; packaged EXE is available for manual checks.

2. Stage 3.1: source-separated protocol output
   - Status: implemented and accepted.
   - Implemented: each protocol fragment can contain separate `Системный звук:` and `Микрофон:` blocks.
   - Success signal: system speech and microphone speech are visibly separated in the transcript.

3. Stage 3.2: fragment time ranges and duplicate filtering
   - Status: implemented, manually checked, committed, and pushed.
   - Implemented: fragment headers include time ranges, for example `Фрагмент 1 (00:00-00:14)`.
   - Implemented: diagnostic mode for protocol sessions writes per-source WAV files and `protocol_diagnostics.jsonl`.
   - Implemented: microphone duplicate filter mutes microphone intervals that overlap active system audio before microphone recognition.
   - Success signal: system text remains in `Системный звук:`, microphone text remains in `Микрофон:`, and system text is not duplicated in the microphone block.

4. Stage 3.2.1: Russian abbreviation normalization
   - Status: implemented in code and fresh packaged build.
   - Already implemented: Russian-mode postprocessing for a fixed set of frequent abbreviations recognized in Latin letters.
   - Already implemented cases: `DPS -> ДПС`, `PDD -> ПДД`, `DTP -> ДТП`, `GIBDD -> ГИБДД`, `MVD -> МВД`, `FSB -> ФСБ`, `RF -> РФ`, `OSAGO -> ОСАГО`, `CASCO/KASKO -> КАСКО`.
   - Implemented: a general Cyrillic conversion rule for Latin CAPS abbreviations in Russian text.
   - Implemented: a stop-list for abbreviations that should stay Latin, such as `GPS`, `USB`, `API`, `CPU`, `GPU`, `HTML`, `PDF`, `URL`, `HTTP`.
   - Implemented: tests for spaced/dotted forms, such as `D P S`, `D.P.S.`, and abbreviations near Russian context.
   - Constraint: apply only in Russian recognition mode so English dictation and real Latin names are not damaged.
   - Success signal: common Russian abbreviations appear in Cyrillic through a general rule, while technical/international abbreviations from the stop-list stay Latin.

5. Stage 3.3: chunk stitching and repeated tails
   - Status: implemented in code and fresh packaged build.
   - Problem: Whisper can repeat phrases at chunk boundaries, and the issue becomes more visible on long recordings.
   - Implemented: compare the end of the previous fragment with the beginning of the next fragment per source.
   - Implemented: remove obvious repeated tails only when the overlap is exact, long enough, and ends at a clear phrase boundary.
   - Implemented: avoid aggressive smart rewriting so meaningful text is not lost.
   - Implemented: tests for repeated boundary phrases, duplicate-only chunks, and conservative non-removal.
   - Success signal: long recordings do not contain obvious repetitions at fragment boundaries.

6. Stage 3.4: protocol quality polish
   - Status: implemented in code and fresh packaged build.
   - Implemented: protocol output starts with the neutral document title `Черновик протокола`.
   - Implemented: fragment headers use neutral draft formatting, for example `Фрагмент 1 · 00:00-01:00`.
   - Implemented: no invented sections such as decisions or tasks are generated.
   - Implemented: the full draft remains plain editable/copyable text.
   - Constraint: ordinary dictation output is unchanged.
   - Success signal: protocol output looks like a draft protocol, not a recognition log.

7. Stage 3.5: long-recording UI
   - Status: implemented in code and fresh packaged build.
   - Problem: during long recognition the user must understand that Dicta is working and has not frozen.
   - Implemented: show a compact counter on the right side of the lower status bar.
   - Implemented: keep the protocol status empty while Dicta is idle, instead of showing `Протокол: -`.
   - Implemented: show clear states: `Запись`, `Обработка фрагмента`, `Протокол готов`.
   - Implemented: count silent/no-text chunks as processed so long recognition does not look stuck.
   - Implemented: keep the protocol status readable in windowed mode by moving it to a second lower-bar row when the window is too narrow.
   - Implemented: show real system clock time in visible protocol fragment headers instead of only technical offsets from recording start.
   - Implemented: filter long same-fragment system-audio repeats out of the microphone block while preserving short unique microphone phrases.
   - Implemented: mark clearly low-quality protocol sentences as `[неразборчиво]` when Windows spellcheck sees a dense cluster of invalid words.
   - Implemented: keep mini-panel and tray code paths unchanged except existing recognition cancel behavior.
   - Validation: quick tests and packaged EXE tests passed; full manual regression remains in stage 3.6.
   - Success signal: during a long recording it is clear that Dicta has not frozen.

8. Stage 3.6: reliability and manual verification
   - Status: automated/package verification executed; real audio manual checks remain before closing the stage.
   - Passed: source quick tests and packaged EXE quick tests for formatting and post-processing.
   - Passed: packaged `dist\DictaProtocol` verification; manifest and SHA256 checks completed.
   - Passed: packaged diagnostic completed with zero blocking failures.
   - Passed: packaged EXE launches, a second instance exits and restores the existing window, and minimizing shows the tray mini-panel.
   - Passed: a short silent recording can be started, minimized, and stopped from the mini-panel; the mini-panel returns to the record state.
   - Warning: microphone diagnostics opened devices but measured 0% peak, so microphone speech recognition cannot be accepted from automation alone.
   - Warning: packaged diagnostic reported no Dicta firewall rule and temporary Dicta files in `%TEMP%`; network audit was intentionally skipped.
   - Pending manual check: short microphone-only recording with real speech.
   - Pending manual check: short system-audio-only recording with real playback.
   - Pending manual check: combined recording with system audio and microphone.
   - Pending manual check: 3-5 minute recording.
   - Pending manual check: recording with one real source silent while the other has audio.
   - Success signal: stage 3 behavior passes the full manual verification set in the packaged EXE.

9. Stage 4: source separation quality
   - Status: approved plan after stage 3.6.
   - Goal: improve the practical separation of `Системный звук` and `Микрофон` in protocol mode without requiring a heavier model or cloud services.
   - Principle: if a microphone block is mostly leaked system audio or recognition garbage, do not show it as microphone speech.
   - Constraint: keep ordinary dictation unchanged.

10. Stage 4.1: separation diagnostics
    - Planned: write per-fragment diagnostics for system activity duration, microphone activity duration, muted microphone duration, and text similarity between sources.
    - Planned: include enough data to explain why a microphone block was kept, removed, or marked unclear.
    - Success signal: after a bad combined recording, diagnostics show whether the microphone block was real speech, leaked system audio, or unclear audio.

11. Stage 4.2: delayed system-audio leakage
    - Planned: account for small delay between system audio playback and the same sound reaching the microphone.
    - Planned: test several conservative offsets around system activity before muting microphone spans.
    - Constraint: do not remove independent microphone phrases that happen shortly before or after system speech.
    - Success signal: microphone blocks contain fewer delayed copies of system audio.

12. Stage 4.3: hide non-microphone blocks
    - Planned: if the microphone result is mostly the system-audio text, hide the microphone block entirely instead of showing duplicate text or `[неразборчиво]`.
    - Planned: keep short unique microphone phrases when they are separable from the system repeat.
    - Success signal: the protocol does not present leaked system audio as microphone speech.

13. Stage 4.4: source-quality manual regression
    - Planned: check YouTube/system playback with short microphone comments.
    - Planned: check pauses, one-source silence, and simultaneous speech.
    - Planned: confirm that useful microphone phrases remain visible and leaked/mixed blocks are removed or marked unclear.
    - Success signal: the protocol is cleaner in the known bad cases without hiding real microphone comments.

## Stage 3 Work Order

1. First implement separate recognition of system audio and microphone.
2. Then add fragment time ranges.
3. Then remove repeated text at fragment boundaries.
4. Then improve UI statuses.
5. Finally build the EXE and run manual verification.

## Stage 3 Out Of Scope

- Do not identify speakers.
- Do not generate automatic decisions or tasks.
- Do not build a complex AI protocol.
- Do not add cloud services.
- Do not break existing ordinary dictation.

## Maintenance Notes

- Keep Dicta plans here, not in archived workspaces under `C:\Users\Olga\Documents\Codex\...`.
- Keep long verification output in `artifacts`.
- Keep user-facing procedure updates in `docs\USER_CHECKLIST.md`.
- Keep architecture and behavioral decisions in `docs\decision-log.md`.
- Build this branch with `.\scripts\build_dicta_exe.ps1 -PackageVersion "1.1-pilot-protocol" -DistRoot "dist\DictaProtocol"`.
- When reporting the ready EXE for manual checks, use a clickable Markdown file link to the absolute path.
