# Dicta Decision Log

Last updated: 2026-05-26

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

Reason:

- Whisper recognition expects mono PCM, but some USB headsets reject direct mono or 16000 Hz opening.
- Downmixing inside Dicta preserves the existing mono recording pipeline while accepting more devices.

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
