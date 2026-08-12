# Project agent rules

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
