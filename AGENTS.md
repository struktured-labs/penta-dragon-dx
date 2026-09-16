# Project agent rules

## Issue-first bug-fix workflow

- Before implementing a bug fix, find an existing matching GitHub issue or
  create one in `struktured-labs/penta-dragon-dx`. Avoid duplicate reports.
- Record the observed behavior, expected behavior, known reproduction steps,
  and release impact. Distinguish player reports from verified findings; do
  not invent a cause or mark an unqualified trial as fixed.
- After the issue exists, implement the fix and add or run appropriate
  regression tests. Reference the issue in the fix and verification notes.
- Keep the issue open while validation is incomplete. Close it only after
  the fix is verified or the user explicitly directs closure.
- Read-only investigation may precede filing when needed to identify the
  problem or locate a duplicate, but implementation must follow filing.

## Scratch-artifact locations

- Never use the system `/tmp` directory for this project.
- Use the repository-local ignored `tmp/` directory for ordinary temporary
  builds, receipts, traces, screenshots, and other scratch artifacts.
- Use `/mnt/data/tmp/` for large scratch artifacts such as long videos,
  frame sequences, large capture galleries, and bulky emulator corpora.
- If `/mnt/data/tmp/` is unavailable or not writable, keep the artifact in
  repository-local `tmp/`; never fall back to the system `/tmp` directory.
- Keep ROMs, save data, savestates, captures, and other generated scratch
  artifacts out of Git regardless of which scratch location owns them.

## Hard emulator-safety gate

- Never invoke `mgba`, `mgba-qt`, `mgba-headless`, or `xvfb-run ... mgba`
  directly.
- Headed human play must use `scripts/launch_mgba.sh`. Automated verifiers
  must use their checked-in single-flight default. Never override `--mgba`
  with an unguarded executable.
- Never run two emulator-backed commands concurrently, including through
  parallel tool calls, background jobs, subagents, or shell fan-out.
- The project-wide lock is fail-closed: exit status 75 means another emulator
  owns the slot. Wait for that exact owner to finish; do not bypass the lock.
- Never use broad `pkill`, `killall`, or pattern-based process termination.
  Stop only the exact launcher/emulator PID owned by the current command.
- Every emulator launch must remain a child of its verifier/launcher. The
  single-flight wrapper arms Linux parent-death cleanup and execs the emulator
  so parent timeouts cannot strand a Qt process.
- After any interrupted emulator run, use the read-only process check and
  report the result before starting another. Do not launch an emulator merely
  to test the guard.

## Analogue Pocket deployment

- Every Pocket SD deployment must copy the verified candidate twice into
  `Assets/gbc/common/`: once as the immutable hash-qualified filename and once
  as `Penta Dragon DX v3.01.gbc` for convenient selection on the device.
- Never overwrite a hash-qualified ROM. The unqualified filename is the
  deliberate latest-candidate alias and may be updated only after the source
  candidate has passed its required gates.
- Flush the card and verify that both deployed files match the source ROM's
  SHA-256 before safely unmounting it.

## Codex Stage-1 Stop gate

- Keep the single repo-local Stop command in `.codex/hooks.json` enabled and
  trusted. It must run on every Stop; prose, `stop_hook_active`, and a claimed
  test result are never bypasses.
- A READY claim requires the exact pinned candidate, manifests, current tool
  identities, fresh nested evidence, and exact tested-ROM path/SHA provenance.
  Stale, unknown, or differently hashed playtests block the turn.
- After changing the hook definition, review and trust it with `/hooks`, then
  start a fresh Codex session so project hook discovery is guaranteed.
