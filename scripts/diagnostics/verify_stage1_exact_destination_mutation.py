#!/usr/bin/env python3
"""Prove the moving-hazard gate catches loss of the completed-map address."""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: run_gate invokes the checked
# verify_low_health_hazard_determinism entrypoint, which owns single-flight.

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v302_title_fix import (  # noqa: E402
    STAGE1_HAZARD_PURE_MAP_ADDR,
    STAGE1_HAZARD_ROW_HELPER_ADDR,
    build_stage1_hazard_row_helper,
)


DETERMINISM = Path(__file__).with_name(
    "verify_low_health_hazard_determinism.py"
)
AUTHORITATIVE_DESTINATION = bytes.fromhex(
    "7C B7 20 08 FA 0B DC 87 87 EE 98 67"
)
R451C_SHA256 = "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892"
R453_SHA256 = "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b"
R455_SHA256 = "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9"
R456C_SHA256 = "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4"
R456D_SHA256 = "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722"
R527_SHA256 = "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b"
R528_SHA256 = "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50"
R529_SHA256 = "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208"
R530_SHA256 = "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30"
R531_SHA256 = "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855"
R532_SHA256 = "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821"
R533_SHA256 = "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba"
R534_SHA256 = "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
R535_TILE_RETIRE_SHA256 = "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3"
R535_STAGE_CARD_BLACK_SHA256 = "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576"
R536_PENTA_SEAM_SHA256 = "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350"
R535_STAGE1_ONLY_CARD_BLACK_SHA256 = "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96"
R536_STAGE1_ONLY_CARD_BLACK_SHA256 = "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63"
# r451c carries the current semantic-helper ABI (the destination contract is
# unchanged, but the preceding selector bytes differ from the older builder
# helper). Keep its exact authenticated prefix explicit rather than accepting
# arbitrary candidate-owned bytes.
R451C_HELPER_PREFIX = bytes.fromhex(
    "C1 FA 80 D8 47 F0 B7 FE 02 20 38 FA FD DC B7 CA 50 6C 78 FE 0A 28 0C F0 BD FE 12 28 06 3D FE 0C D2 50 6C FA 5B DF E6 03 FE 03 C2 50 6C 7C B7 20 08 FA 0B DC 87 87 EE 98 67 2E 00"
)
# Flip H between $98/$9C, then fall through at the original
# destination_ready label. This forces the completed publication onto the peer
# physical map without writing outside either tilemap or perturbing gameplay
# RAM, making the visual negative control deterministic and architecture-local.
FORCED_WRONG_DESTINATION = bytes.fromhex(
    "7C EE 04 67 00 00 00 00 00 00 00 00"
)


def digest(data: bytes | Path) -> str:
    if isinstance(data, Path):
        data = data.read_bytes()
    return hashlib.sha256(data).hexdigest()


def run_gate(rom: Path, output: Path, timeout: float, state: Path | None = None,
             hazard_receipt: Path | None = None) -> tuple[int, dict, str]:
    command = [
        sys.executable,
        str(DETERMINISM),
        str(rom),
        "--output", str(output),
        "--samples", "417",
        "--post-trigger-keys", "0x41",
        "--require-hazard-attributes",
        "--require-hazard-publication-owner",
        "--timeout", str(timeout),
    ]
    if state is not None and hazard_receipt is not None:
        command[command.index("--samples") + 1] = "240"
        command.extend([
            "--state", str(state), "--boot-derived-state",
            "--hazard-state-receipt", str(hazard_receipt),
            "--scene0b-frames", "120",
            "--require-scene0b-low-health",
            "--trace-scanner",
        ])
    else:
        command.insert(command.index("--require-hazard-attributes"),
                       "--require-music-transition")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout * 2 + 45,
        check=False,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "verifier.log").write_text(completed.stdout)
    receipt_path = output / "receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    return completed.returncode, receipt, completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--state-receipt", type=Path)
    args = parser.parse_args()

    source_path = args.rom.resolve()
    source = source_path.read_bytes()
    helper, _ = build_stage1_hazard_row_helper()
    relative = helper.find(AUTHORITATIVE_DESTINATION)
    if relative < 0 or helper.find(AUTHORITATIVE_DESTINATION, relative + 1) >= 0:
        raise SystemExit("FAIL: expected one authoritative-destination instruction")
    # The release-lock candidate (db09de8d) is accepted with the c693/4f5a
    # lineage below: its delta leaves bank 19 untouched (release_lock_lineage).
    # Expanded releases relocate the private Stage-1 helper from build-time
    # bank 14 to bank 19. The fixed mapper's immediate byte is the runtime
    # authority and keeps this control valid for both layouts.
    stage1_code_bank = source[STAGE1_HAZARD_PURE_MAP_ADDR + 1]
    helper_offset = (
        stage1_code_bank * 0x4000
        + STAGE1_HAZARD_ROW_HELPER_ADDR - 0x4000
    )
    # The expanded combiner overlays immutable bank-1 hazard art into padding
    # later in this same allocation. The executable prefix through this
    # instruction remains exact and is the only portion this mutation owns.
    prefix_end = relative + len(AUTHORITATIVE_DESTINATION)
    source_sha256 = digest(source)
    expected_prefix = (
        R451C_HELPER_PREFIX
        if source_sha256 in {R451C_SHA256, R453_SHA256, R455_SHA256, R456C_SHA256, R456D_SHA256, R527_SHA256, R528_SHA256, R529_SHA256, R530_SHA256, R531_SHA256, R532_SHA256, R533_SHA256, R534_SHA256, R535_TILE_RETIRE_SHA256, R535_STAGE_CARD_BLACK_SHA256, R536_PENTA_SEAM_SHA256, "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b", "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d", "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5", "db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8", R535_STAGE1_ONLY_CARD_BLACK_SHA256, R536_STAGE1_ONLY_CARD_BLACK_SHA256}
        else helper[:prefix_end]
    )
    if source[helper_offset:helper_offset + len(expected_prefix)] != expected_prefix:
        raise SystemExit(
            "FAIL: candidate does not embed the exact reviewed helper prefix"
        )
    mutation_offset = helper_offset + relative

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    mutant = bytearray(source)
    mutant[
        mutation_offset:mutation_offset + len(AUTHORITATIVE_DESTINATION)
    ] = FORCED_WRONG_DESTINATION
    mutant_path = output / "candidate-forced-to-wrong-map-page.gb"
    mutant_path.write_bytes(mutant)

    uses_current_hazard_fixture = source_sha256 in {R451C_SHA256, R453_SHA256, R455_SHA256, R456C_SHA256, R456D_SHA256, R527_SHA256, R528_SHA256, R529_SHA256, R530_SHA256, R531_SHA256, R532_SHA256, R533_SHA256, R534_SHA256, R535_TILE_RETIRE_SHA256, R535_STAGE_CARD_BLACK_SHA256, R536_PENTA_SEAM_SHA256, "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b", "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d", "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5", "db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8", R535_STAGE1_ONLY_CARD_BLACK_SHA256, R536_STAGE1_ONLY_CARD_BLACK_SHA256}
    # The state was captured from the clean candidate before this exact
    # helper-only mutation.  Authenticate that reuse explicitly; the child
    # verifier still checks the mutated ROM hash and the unchanged state hash.
    source_state = (args.state or
                    Path("tmp/r451c-hazard-state/stage1-hazard.ss0")).resolve()
    source_receipt = (args.state_receipt or
                      Path("tmp/r451c-hazard-state/receipt.json")).resolve()
    mutant_receipt_path = output / "mutant-hazard-state-receipt.json"
    if uses_current_hazard_fixture:
        if not source_state.is_file() or not source_receipt.is_file():
            raise SystemExit(
                "FAIL: fresh candidate-owned hazard-state evidence is required"
            )
        source_hazard = json.loads(source_receipt.read_text())
        mutant_receipt = dict(source_hazard)
        mutant_receipt.update({
        "schema": "penta-stage1-hazard-state-mutation-fixture-v1",
        "rom": str(mutant_path.resolve()),
        "rom_sha256": digest(mutant),
        "source_rom": str(source_path),
        "source_rom_sha256": digest(source),
        "state": str(source_state),
        "state_sha256": digest(source_state),
        "mutation_fixture": {
            "kind": "exact-destination-negative-control",
            "source_rom_sha256": digest(source),
            "state_sha256": digest(source_state),
        },
        })
        mutant_receipt_path.write_text(json.dumps(mutant_receipt, indent=2) + "\n")
    else:
        source_state = source_receipt = None

    clean_status, clean, _ = run_gate(
        source_path, output / "clean", args.timeout,
        source_state, source_receipt,
    )
    mutant_status, mutated, _ = run_gate(
        mutant_path, output / "mutated", args.timeout,
        source_state, mutant_receipt_path if uses_current_hazard_fixture else None,
    )
    mutant_replays = mutated.get("replays", [])
    mutant_visible_failures = [
        replay.get("hazard_mismatch_frames", {}).get("total", 0)
        for replay in mutant_replays
    ]
    checks = {
        "clean exact-destination candidate passes both moving replays": (
            clean_status == 0 and clean.get("passed") is True
        ),
        "forced wrong map page fails the moving hazard gate": (
            mutant_status != 0 and mutated.get("passed") is False
        ),
        "both mutant replays render raw hazard mismatches": (
            len(mutant_visible_failures) == 2
            and all(count > 0 for count in mutant_visible_failures)
        ),
        "mutant replays remain deterministic after bounded phase alignment": (
            mutated.get("alignment", {}).get("passed") is True
        ),
        "mutation changes only destination selection to the peer map": (
            sum(left != right for left, right in zip(source, mutant))
            == sum(
                left != right for left, right in zip(
                    AUTHORITATIVE_DESTINATION,
                    FORCED_WRONG_DESTINATION,
                )
            )
            and mutant[
                mutation_offset:mutation_offset
                + len(FORCED_WRONG_DESTINATION)
            ] == FORCED_WRONG_DESTINATION
        ),
    }
    receipt = {
        "schema": "penta-stage1-exact-destination-mutation-v1",
        "source_rom": str(source_path),
        "source_sha256": digest(source),
        "mutant_rom": str(mutant_path),
        "mutant_sha256": digest(mutant),
        "mutation_offset": f"0x{mutation_offset:05X}",
        "stage1_code_bank": stage1_code_bank,
        "before": AUTHORITATIVE_DESTINATION.hex().upper(),
        "after": FORCED_WRONG_DESTINATION.hex().upper(),
        "clean_receipt": str(output / "clean" / "receipt.json"),
        "mutant_receipt": str(output / "mutated" / "receipt.json"),
        "mutant_visible_failure_frames": mutant_visible_failures,
        "checks": checks,
        "passed": all(checks.values()),
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        print("FAIL: " + "; ".join(failed))
        print(f"Receipt: {receipt_path}")
        return 1
    print(
        "PASS: the exact completed-map destination stays clean, while a "
        "peer-map regression fails deterministically"
    )
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
