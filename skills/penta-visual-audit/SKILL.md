---
name: penta-visual-audit
description: Build, refresh, verify, inspect, and serve the Penta Dragon DX whole-game visual audit. Use for release visual QA, palette audits, screenshot galleries, OG/DX comparisons, stage/boss/miniboss/monster/pickup/projectile/cutscene coverage, stream-readiness review, or when a user asks for visual receipts instead of claims.
---

# Penta Visual Audit

Produce one candidate-bound audit with two independent layers:

- Machine verification proves provenance, hashes, expected inventory, replay determinism, palette metadata, image validity, and explicit coverage gaps.
- Human verification presents the proof in a searchable browser, records `looks good`, `visual issue`, `needs recapture`, or `intentional`, and exports the reviewer record.

Read [references/coverage.md](references/coverage.md) before changing coverage, interpreting a failure, or refreshing the site.

## Safety and truthfulness

- Obey the repository `AGENTS.md`. Never use system `/tmp`; never launch an unguarded emulator; never overlap emulator-backed commands.
- Keep the ROM, saves, states, captures, videos, site builds, and review exports in ignored `tmp/` or `/mnt/data/tmp/`.
- Admit screenshots only through the deterministic-suite matrix or an explicit supplemental receipt bound to the exact candidate SHA-256.
- Never turn context-only screenshots, filenames, or a visually plausible frame into a machine pass.
- Never treat machine coverage as the human verdict. Never infer the user's thumbs-up.
- Before sharing the site, inspect flagged blanks, contact sheets, and representative OG/DX evidence. Fix obvious ROM or harness defects in scope, rebuild, and re-run verification. Leave unresolved items red and say why.

## Refresh workflow

1. Run or identify one fully passing deterministic-suite directory. Call it `<suite-root>` below. Resolve the candidate from `<suite-root>/release-receipt.json` and verify that its hash matches `<suite-root>/matrix/manifest.json`; never substitute `docs/release/verification/latest.json` for an unpromoted audit candidate.
2. Check that no mGBA process is running with `scripts/check_emulator_processes.sh --require-none`.
3. Capture missing supplemental families serially. For the current complete catalog:

   ```bash
   python3 scripts/diagnostics/capture_all_minibosses.py \
     <suite-root>/build/candidate-a.gb \
     --output tmp/visual-audit-evidence/minibosses --determinism-replays 2

   python3 scripts/diagnostics/capture_projectile_visual_audit.py \
     <suite-root>/build/candidate-a.gb \
     --output tmp/visual-audit-evidence/projectiles --determinism-replays 2
   ```

   Exit 75 means another emulator owns the slot; wait for that exact owner and do not bypass the lock. After any interrupted run, perform the read-only process check required by `AGENTS.md` before continuing.

4. Build from one evidence root:

   ```bash
   python3 scripts/diagnostics/build_visual_audit.py \
     --evidence-root <suite-root>/matrix/artifacts \
     --release-receipt <suite-root>/release-receipt.json \
     --miniboss-receipt tmp/visual-audit-evidence/minibosses/receipt.json \
     --projectile-receipt tmp/visual-audit-evidence/projectiles/receipt.json \
     --output tmp/visual-audit-site --strict
   ```

5. Verify the static result independently:

   ```bash
   python3 scripts/diagnostics/verify_visual_audit.py \
     tmp/visual-audit-site --strict
   ```

6. Rebuild once into a second owned directory and compare `CHECKSUMS.sha256`; site determinism is a release requirement, not an optional diagnostic.
7. Serve only a verified build:

   ```bash
   python3 scripts/diagnostics/serve_visual_audit.py \
     tmp/visual-audit-site --host 127.0.0.1 --port 8766
   ```

Use a reachable host or tunnel only when the user explicitly needs remote access. Report the candidate hash, covered/expected count, machine gaps, suspicious images, and review-export behavior with the link.

## Review and iteration

- Use category, machine-state, human-state, side, and text filters to isolate problems.
- For OG/DX comparisons, compare paired phase/input samples; do not claim timing or intent from unrelated frames.
- Use displayed YAML swatches as expected palette context, then judge containment, coherence, silhouette completeness, flicker clues, and stray geometry.
- Export the browser review JSON before replacing the build. Import it after refresh; audit IDs are stable catalog keys.
- Convert every accepted bug fix into a deterministic verifier or catalog requirement before presenting the next candidate.

Do not commit generated audit output. Commit only the skill, catalog, deterministic capture/build/verification code, and durable documentation when requested.
