# Dicta Plans

Last updated: 2026-06-08

This file is the Dicta-specific project plan. Global Codex operating rules belong in `C:\Users\Olga\.codex\AGENTS.md`.

## Current Branch

- Branch: `DictaProtocol`.
- Packaged EXE for manual checks: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.
- Latest pushed protocol commit: `a055042 Improve mini panel controls and abbreviation normalization`.
- Current local work after that commit contains stage 3.3 chunk stitching, `-DistRoot` build-script support, stage 3.4 draft protocol formatting, and restored stage 3.5/3.6 planning; commit/push is still pending.
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
   - Status: next planned work after 3.4.
   - Problem: during long recognition the user must understand that Dicta is working and has not frozen.
   - Planned: show a counter such as `Фрагментов готово: 2/5`.
   - Planned: show clear states: `Запись`, `Обработка фрагмента`, `Протокол готов`.
   - Planned: keep the interface responsive or at least visibly busy with an understandable status.
   - Planned: preserve tray and mini-panel behavior without regressions.
   - Success signal: during a long recording it is clear that Dicta has not frozen.

8. Stage 3.6: reliability and manual verification
   - Status: planned after 3.5.
   - Planned check: short microphone-only recording.
   - Planned check: short system-audio-only recording.
   - Planned check: combined recording with system audio and microphone.
   - Planned check: 3-5 minute recording.
   - Planned check: recording with silence in one source.
   - Planned check: minimize to tray during recording.
   - Planned check: stop recording from the mini-panel.
   - Planned check: launch a second app instance and verify the existing window opens.
   - Success signal: stage 3 behavior passes the minimum manual verification set in the packaged EXE.

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
