# Dicta Plans

Last updated: 2026-06-07

This file is the Dicta-specific project plan. Global Codex operating rules belong in `C:\Users\Olga\.codex\AGENTS.md`.

## Current Branch

- Branch: `DictaProtocol`.
- Packaged EXE for manual checks: `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.
- Latest pushed protocol commit: `e883b06 Add protocol microphone duplicate filter`.
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
   - Status: next planned work.
   - Problem: Whisper can repeat phrases at chunk boundaries, and the issue becomes more visible on long recordings.
   - Planned: compare the end of the previous fragment with the beginning of the next fragment.
   - Planned: remove obvious repeated tails.
   - Planned: avoid aggressive smart rewriting so meaningful text is not lost.
   - Planned: add tests for repeated boundary phrases.
   - Success signal: long recordings do not contain obvious repetitions at fragment boundaries.

6. Stage 3.4: protocol quality polish
   - Status: pending after 3.3.
   - Planned: collect more manual protocol examples, tune chunking/source labels if needed, and decide whether diagnostic mode remains visible or moves behind a support-only option.
   - Success signal: long meeting transcripts stay readable, source attribution is stable, and support diagnostics remain available when needed.

## Maintenance Notes

- Keep Dicta plans here, not in archived workspaces under `C:\Users\Olga\Documents\Codex\...`.
- Keep long verification output in `artifacts`.
- Keep user-facing procedure updates in `docs\USER_CHECKLIST.md`.
- Keep architecture and behavioral decisions in `docs\decision-log.md`.
