# Project Codex Rules

- Keep command output compact during long coding sessions: prefer filtered output, tails, summaries, or artifact files instead of pasting full logs into chat.
- For heavy diagnostics and test runs, use one-shot or narrowly scoped commands and summarize only the result, failures, and artifact paths.
- After a large investigation, verification checkpoint, or `WAITING_REVIEW` handoff, start a fresh/forked session before continuing substantial new work.
- Monitor context growth with `C:\Users\Olga\.codex\scripts\codex-context-watch.ps1`; at 85% checkpoint, at 92% fork or start a fresh session.
- When providing a clickable link to `Dicta.exe` for manual verification, also provide current context-fill information and a recommendation on whether to continue in the current chat or move to a new chat. Base the recommendation on the expected complexity of the next task:
  - small verification or minor text/doc fix: current chat is acceptable if context is not near the checkpoint;
  - feature work, packaging changes, audio diagnostics, or IB/security changes: recommend a new chat when context is high or the next step is multi-stage;
  - if context is at or above the checkpoint threshold, recommend starting a new chat before the next substantial stage.
