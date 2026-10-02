---
name: redmage
description: Use Redmage, struktured's secondary AMD/X11 automation box, for remote commands, headed GUI or browser automation, CPU compute, storage, VNC, or system-status checks. Trigger on Redmage, the AMD box, the other automation box, or requests to offload suitable work there.
---

# Redmage

Use Redmage when a task benefits from its 16 CPU threads, available disk, or native X11 session. Project rules and the user's authorization boundaries still apply remotely.

## Connection

- SSH alias: `redmage` (`100.77.58.119` over Tailscale)
- Linux user: `struktured`
- Key: `~/.ssh/redmage_key`
- Hardware: Ryzen 7 6800H, 8C/16T; about 30 GB usable RAM; Radeon 680M; about 740 GB root disk

Use fail-fast, non-interactive SSH:

```bash
ssh -o BatchMode=yes redmage '<command>'
```

Do not expose key material or copy credentials into a project. If SSH fails, report whether the host is unreachable, Windows-booted, or rejecting authentication; do not retry indefinitely.

## Safe offload workflow

Check remote state before changing it:

```bash
ssh -o BatchMode=yes redmage 'hostname; uptime; df -h /; ps -eo pid,ppid,stat,comm,args'
```

Use an explicit remote project/scratch directory and record input/output hashes. Keep generated ROMs, savestates, captures, and other scratch artifacts out of Git. For Penta Dragon DX, local artifacts must remain under repository `tmp/` or `/mnt/data/tmp/`; never pull them into system `/tmp`.

Never use broad `pkill`, `killall`, or pattern-based termination. Stop only a PID owned by the current remote command.

### Penta Dragon DX emulator gate

The repository's single-flight rule spans all machines used for the task. Never start an emulator-backed command on Redmage while one is running locally, and never start a local emulator while a Redmage emulator job is active. Use checked-in launchers/verifiers only; do not invoke mGBA executables directly. Static analysis, builds, hashing, and capture post-processing may run in parallel when they do not race shared outputs.

## Headed X11 applications

Graphical programs require `DISPLAY=:0`. Detach them cleanly so SSH does not hang:

```bash
ssh -o BatchMode=yes redmage \
  'DISPLAY=:0 setsid <app> </dev/null >$HOME/redmage-app.log 2>&1 &'
```

Verify the desktop session before relying on synthetic input:

```bash
ssh -o BatchMode=yes redmage \
  'DISPLAY=:0 loginctl show-session $(loginctl | awk "$0 ~ /seat0/ {print \\$1; exit}") -p Type'
```

Expected type is `x11`. With X11, use `DISPLAY=:0 wmctrl`, `xdotool`, and `scrot`. A blank screenshot may mean DPMS or screen blanking is active; inspect `DISPLAY=:0 xset q`.

## Headed browser automation

Redmage has a persistent real-Chrome profile suitable for sites that reject headless fingerprints:

```bash
ssh -o BatchMode=yes redmage \
  'setsid $HOME/start-automation-chrome.sh </dev/null >$HOME/automation-chrome.log 2>&1 &'
```

Attach through Chrome DevTools Protocol rather than launching automation Chromium. Plain Playwright is preferred; Patchright is a fallback for hostile detection. User login and unsolved interactive challenges remain manual—notify the user instead of burning repeated attempts.

For VNC or CDP, tunnel localhost-only ports with the Redmage key. Do not open them publicly.

## Compute notes

Redmage's CPU is the useful resource. Its `gfx1035` integrated GPU is not a ROCm target; for local-model experimentation use llama.cpp's Vulkan backend, not ROCm/Ollama-ROCm. Shared DDR5 makes it suitable for small or mid-sized quantized models, not heavy GPU workloads.

Redmage dual-boots Windows. If the Linux SSH identity is unavailable but the host responds differently, stop and report that it may be Windows-booted rather than improvising PowerShell commands unless the user asks.

Last known-good environment (2026-08-23): KDE X11 at `:0`, headed Chrome with Radeon rendering, working `xdotool`, `wmctrl`, `scrot`, and localhost-only `x11vnc`.
