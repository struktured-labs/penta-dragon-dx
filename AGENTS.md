# Project agent rules

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
