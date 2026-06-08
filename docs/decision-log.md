# Dicta Decision Log

Last updated: 2026-06-08

This file records Dicta-specific decisions. Global Codex rules belong in `C:\Users\Olga\.codex\AGENTS.md`.

## 2026-05-24: Separate Global And Project Codex Rules

Decision:

- Keep common Codex operating rules only in `C:\Users\Olga\.codex\AGENTS.md`.
- Keep only Dicta-specific rules in `C:\Users\Olga\Documents\VoiceHelper\AGENTS.md`.
- Keep Dicta continuity docs in `C:\Users\Olga\Documents\VoiceHelper\docs`.
- Do not treat similarly named files in `C:\Users\Olga\Documents\Codex\...` or other projects as source of truth for Dicta.

Reason:

- Duplicated global rules drift across projects and make it unclear which instructions are current.
- Dicta needs local rules only for package layout, executable path, no-commit/no-push policy, and verification workflow.

## 2026-05-24: Microphone Grouping And Fallback Order

Decision:

- Keep the user-facing microphone list grouped by readable device names.
- Keep normal Windows audio backends first.
- Use hidden/technical backend devices, such as WDM-KS, only as last fallback.
- If a WDM-KS device has the same cleaned name as a visible device, append it to the same group after visible backends.
- If a device exists only as technical fallback, show it with a `тех. fallback` marker.

Reason:

- Users should not have to choose from technical MME/DirectSound/WASAPI/WDM-KS duplicates.
- Some USB headsets or Windows driver stacks only work through a non-preferred backend, so the fallback must remain available.

## 2026-05-24: Microphone Open Modes

Decision:

- Try sample rates in this order: `16000`, device default samplerate, `48000`, `44100`, `32000`.
- Try `1` input channel first.
- If the device supports it, try `2` input channels and downmix PCM16 to mono before recording, level measurement, and recognition.
- Try raw input formats in order: `int16`, `float32`, `int24`, `int32`; convert non-PCM16 samples to PCM16 mono inside Dicta.

Reason:

- Whisper recognition expects mono PCM, but some USB headsets reject direct mono or 16000 Hz opening.
- Downmixing inside Dicta preserves the existing mono recording pipeline while accepting more devices.
- Some Windows USB PnP/WASAPI stacks reject one sample format while accepting another common capture format.

## 2026-05-24: "Найти микрофон" Runs In Background

Decision:

- Add a "Найти микрофон" button near "Обновить" and "Проверить".
- Run microphone probing in a worker thread.
- Show progress and peak level through the Tk UI queue.
- Disable conflicting controls while probing, then restore them when the search finishes.

Reason:

- Probing several backends, sample rates, and channel counts can take several seconds.
- The app must not look frozen while Dicta is testing unknown USB hardware.

## 2026-05-24: Microphone Diagnostics

Decision:

- Add `Dicta.exe --microphone-diagnostics --seconds N`.
- Include grouped device name, physical/backend device list, opened mode, peak level, stream status, and recent open errors.
- Run the new check from `scripts\diagnose_dicta.ps1` as "Microphone quick open test".
- Use `Start-Process` with stdout/stderr redirection for windowed `Dicta.exe` diagnostic commands.

Reason:

- A packaged windowed executable does not reliably print stdout to the parent PowerShell console when invoked directly.
- Support needs the exact backend/rate/channel result to understand why a USB headset did not start.

## 2026-05-24: Microphone Fallback Must Start Successfully

Decision:

- Treat an input mode as usable only after `RawInputStream.start()` succeeds.
- If stream creation succeeds but `start()` fails, close that stream and continue trying the next sample rate, channel count, or backend.
- During "Найти микрофон", auto-select only a device that reaches the working peak threshold.
- If no working microphone is found, keep the user's current selection unchanged instead of switching to a silent technical fallback.

Reason:

- Some WASAPI devices accept stream construction for an unsupported format, then fail only on `start()` with `AUDCLNT_E_UNSUPPORTED_FORMAT`.
- Selecting a WDM-KS fallback that opens but stays silent makes the UI look like Dicta chose the wrong microphone.

## 2026-05-24: Settings Save And Cancel Close Window

Decision:

- Add "Сохранить" and "Отмена" buttons to the settings window footer.
- "Сохранить" writes the supported user settings to `settings.json`, updates the in-memory rollback snapshot, and closes the settings window after a successful save.
- "Отмена" restores visible settings controls to the last saved snapshot and closes the settings window.
- Text checkboxes and backend selection no longer auto-save immediately on every click/change.

Reason:

- Users need a clear, visible result after pressing footer buttons; closing the settings window makes it obvious that save/cancel was applied.

## 2026-05-26: Quiet Recordings Use Manual Software Gain

Decision:

- Keep Windows microphone level and driver settings outside Dicta's control.
- Add manual software gain for PCM16 audio before VAD and Whisper recognition.
- Keep gain at `0%` by default through the saved `audio_gain_percent` user setting.
- Show a visible recognition status when gain is applied: selected percent, multiplier, and peak before/after.
- Keep the gain bounded so quiet input can be lifted deliberately without changing good recordings by default.

Reason:

- A tester reported Windows input sensitivity at maximum while Dicta saw recording levels around 10%, causing likely recognition errors.
- Some Windows/USB audio stacks deliver quiet PCM even when the system input level is high.
- Automatic gain can make already-good recordings worse, so the user needs explicit manual control.
- Applying gain inside the app is reproducible, package-local, and easier to diagnose than relying on driver-specific microphone boost controls.

## 2026-06-07: Build Script Uses Explicit DistRoot

Decision:

- Add `-DistRoot` to `scripts\build_dicta_exe.ps1`, with `dist\Dicta` as the default package folder.
- Build DictaProtocol branch packages with `-DistRoot "dist\DictaProtocol"`.
- Stage PyInstaller output under `build\pyinstaller-dist`, then clear and repopulate only the selected package folder under `dist`.
- Reject `-DistRoot` values that resolve outside `dist` or to the `dist` root itself.

Reason:

- DictaProtocol manual checks use `dist\DictaProtocol\Dicta.exe`, while the old build script hardcoded `dist\Dicta`.
- A first-class parameter removes the need for ad hoc post-build package synchronization.
- Restricting the target path keeps package rebuilds scoped to one intended distributable folder.

## 2026-06-07: Ready EXE Link Must Be Clickable

Decision:

- In user-facing final responses, report the ready manual-check EXE as a clickable Markdown file link to the absolute path.
- Keep the DictaProtocol manual-check target at `C:\Users\Olga\Documents\VoiceHelper\dist\DictaProtocol\Dicta.exe`.

Reason:

- The user needs to open the rebuilt package directly from the response.
- A raw path is easy to miss or inconvenient to use inside the Codex desktop app.

## 2026-06-07: Protocol Stitching Stays Conservative

Decision:

- Remove repeated text only at protocol chunk boundaries.
- Compare the end of the previous protocol text with the beginning of the next protocol text per source.
- Require an exact, sufficiently long word overlap that ends at a clear phrase boundary.
- Remove duplicate-only chunks, but keep near matches and short ambiguous overlaps unchanged.

Reason:

- Whisper can repeat a phrase at chunk boundaries during long recordings.
- Aggressive semantic rewriting could remove meaningful meeting text, so the rule must be predictable and easy to test.
- Per-source stitching avoids mixing system-audio context with microphone context.

## 2026-06-08: Protocol Output Is A Draft

Decision:

- Start protocol output with the neutral document title `Черновик протокола`.
- Format fragment headers as `Фрагмент N · start-end`.
- Do not invent semantic sections such as decisions or tasks.
- Keep the protocol draft as plain editable/copyable text.
- Do not change ordinary dictation formatting.

Reason:

- The user needs a draft protocol, not a recognition log.
- Neutral formatting improves readability without pretending to understand meeting decisions.
- Ordinary dictation and protocol mode have different output expectations.

## 2026-06-08: Long Protocol Recognition Shows Fragment Progress

Decision:

- Add a compact protocol status field on the right side of the lower status bar.
- Show `Запись`, `Обработка фрагмента`, and `Протокол готов` states during combined protocol recording and recognition.
- Show an explicit processed-fragment counter during protocol work.
- Count silent/no-text chunks as processed for UI progress, even though they do not add text to the draft protocol.
- Keep mini-panel and tray behavior unchanged except for the existing `Прервать` button state during recognition.

Reason:

- Long recordings can spend minutes in recognition, and the user needs visible evidence that Dicta has not frozen.
- Counting only chunks that produce text would make silence look like a stuck recognizer.
- Keeping the field empty while idle avoids technical noise such as `Протокол: -`.
- Placing it in the existing lower bar avoids adding a permanent second row for users who are not currently processing a protocol.

## 2026-06-08: Protocol Progress Wraps In Narrow Windows

Decision:

- Keep the full protocol progress text, for example `Обработка фрагмента 1/3 · готово 0/3`.
- In wide windows, show it on the right side of the lower status bar.
- In narrow windows, move it to a second lower-bar row instead of clipping or shortening it.
- Keep the second row hidden while the protocol progress text is empty.

Reason:

- The text is useful during long recognition and should not disappear behind the window edge.
- Shortening the text would make the status less clear.
- A conditional second row affects only narrow/busy states and preserves the compact full-screen layout.

## 2026-06-08: Spellcheck Accept Word Action Is User-Facing

Decision:

- Remove `Добавить в словарь Windows` from the main spelling context menu.
- Rename the Dicta word action to `Больше не считать ошибкой`.
- Keep the behavior local to Dicta recognition/spellcheck memory from the user's point of view.

Reason:

- The user should not decide between Dicta and Windows dictionaries during normal correction.
- The expected outcome is simple: the marked word should stop being treated as an error in Dicta.
- Avoid writing to the broader Windows dictionary unless a separate advanced workflow is explicitly needed later.

## 2026-06-08: Protocol Fragment Headers Use Real Clock Time

Decision:

- Visible protocol fragment headers use system clock time from the recording start, for example `Фрагмент 2 · 20:35-20:36`.
- Technical offsets from the beginning of the recording remain available internally and in diagnostics.
- The protocol keeps fragment numbers for navigation, but avoids making the user interpret `01:00-02:00` as a useful meeting timestamp.

Reason:

- A protocol reader needs to tie text to the real meeting timeline, not to the duration of internal audio chunks.
- Clock time is more useful for discussing "when this was said" after the meeting.
- Offsets are still useful for debugging, but they should not be the primary visible protocol signal.

## 2026-06-08: Microphone Blocks Drop Long System Repeats

Decision:

- When a microphone block contains a long same-fragment text span that already appears in the system-audio block, remove that repeated span from the microphone block.
- Preserve short unique microphone phrases before or after the repeated span.
- Keep the rule conservative: it requires a long word overlap and does not try to infer speaker meaning.

Reason:

- In combined recording, system audio can leak into the microphone channel or Whisper can continue a system phrase from a mostly silent microphone chunk.
- The user expects the microphone block to contain microphone speech, not a second copy of the system-audio transcript.
- A conservative overlap filter reduces obvious bad output without deleting short legitimate microphone comments.

## 2026-06-08: Obvious Recognition Garbage Is Marked Unclear

Decision:

- In protocol mode, replace clearly low-quality Russian sentences with `[неразборчиво]`.
- Use Windows Spell Checker as a quality signal: the rule requires a dense cluster of invalid words in one sentence.
- Do not remove a sentence for one or two rare words, names, or terms.
- Keep ordinary dictation unchanged.

Reason:

- On a weak PC, moving to a heavier model is not a reliable primary path.
- Whisper can produce invented words when audio is mixed, noisy, or unclear.
- A protocol should honestly mark unclear audio instead of presenting invented words as real speech.

## 2026-06-08: Stage 4 Prioritizes Hiding Leaked Microphone Blocks

Decision:

- Plan stage 4 around practical separation quality for system audio and microphone.
- If a microphone block is mostly leaked system audio, hide that microphone block entirely.
- Use `[неразборчиво]` for unclear real audio, but do not fill the protocol with unclear markers for blocks that are not useful microphone speech.
- Improve diagnostics first, then delayed leakage handling, then source-quality filtering.

Reason:

- The user needs a cleaner protocol, not a technically exhaustive transcript of every bad microphone artifact.
- Repeating system audio under `Микрофон` is misleading.
- Hiding non-microphone blocks is more readable than showing many noisy placeholders.
