#!/usr/bin/env python3
"""Prove the current-route hazard gate rejects both repaired bug classes."""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: live_receipt receives DEFAULT_MGBA
# from verify_stage1_spike_palettes, which is the checked-in guarded wrapper.

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from verify_stage1_hazard_menu import replay_is_clean, stable_summary
from verify_stage1_spike_palettes import DEFAULT_MGBA, live_receipt
from hazard_mutations_r442 import BASE_SHA as R442_SHA, mutants as r442_mutants


BANK = 19
BANK_SIZE = 0x4000


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bank_offset(address: int, bank: int = BANK) -> int:
    return bank * BANK_SIZE + address - 0x4000


def checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def patch_exact(
    source: bytes, address: int, expected: bytes, replacement: bytes,
    *, bank: int = BANK,
) -> bytes:
    if len(expected) != len(replacement):
        raise AssertionError("mutation must preserve width")
    rom = bytearray(source)
    offset = bank_offset(address, bank)
    if bytes(rom[offset:offset + len(expected)]) != expected:
        raise AssertionError(
            f"mutation preimage at bank {bank}:${address:04X} changed"
        )
    rom[offset:offset + len(replacement)] = replacement
    value = checksum(rom)
    rom[0x014E] = value >> 8
    rom[0x014F] = value & 0xFF
    return bytes(rom)


def patch_fixed_exact(
    source: bytes, address: int, expected: bytes, replacement: bytes,
) -> bytes:
    """Apply one same-width fixed-bank mutation and repair the checksum."""
    if len(expected) != len(replacement):
        raise AssertionError("mutation must preserve width")
    rom = bytearray(source)
    if bytes(rom[address:address + len(expected)]) != expected:
        raise AssertionError(
            f"fixed-bank mutation preimage at ${address:04X} changed"
        )
    rom[address:address + len(replacement)] = replacement
    value = checksum(rom)
    rom[0x014E] = value >> 8
    rom[0x014F] = value & 0xFF
    return bytes(rom)


def run_mutant(
    rom: Path, state: Path, output: Path, timeout: float,
    mutation_base_rom: Path | None = None,
) -> dict:
    replay = live_receipt(
        rom,
        state,
        DEFAULT_MGBA.resolve(),
        output,
        timeout,
        prefix_name="current-hazard-mutant",
        reinitialize=False,
        settle=650,
        input_mask=0,
        screenshot_interval=5,
        expected_room=0x01,
        normalization_writes=((0xD880, 0x02),),
        menu_open=True,
        menu_open_frame=0,
        menu_close_frame=240,
        menu_use_frame=80,
        low_health_frame=270,
        menu_anchor_room=0x01,
        menu_anchor_delay=20,
        trace_routes=False,
        preserve_machine_state=True,
        mutation_base_rom=mutation_base_rom,
    )
    replay["final_screenshot_sha256"] = digest(Path(replay["screenshot"]))
    return replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--state-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    rom = args.rom.resolve()
    state = args.state.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = rom.read_bytes()
    source_sha256 = hashlib.sha256(source).hexdigest()
    state_receipt = json.loads(args.state_receipt.resolve().read_text())
    if (
        state_receipt.get("passed") is not True
        or state_receipt.get("rom_sha256") != source_sha256
        or state_receipt.get("state_sha256") != digest(state)
        or state_receipt.get("hardware", {}).get("settled") is not True
    ):
        raise SystemExit("base cold state is not bound to this ROM")

    phase_target_offset = bank_offset(0x62CB)
    phase_target = source[phase_target_offset:phase_target_offset + 2]
    if phase_target not in {bytes.fromhex("9E 6D"), bytes.fromhex("70 6B")}:
        raise SystemExit(
            "alternate-phase route is neither the private r100 classifier "
            "nor the expanded-bank r101 classifier"
        )
    if phase_target == bytes.fromhex("70 6B"):
        right_span_bank = 20
        dispatcher = source[
            bank_offset(0x4380, right_span_bank):
            bank_offset(0x4400, right_span_bank)
        ]
        signature = bytes.fromhex("7D F6 08 6F 0E 0A")
        if dispatcher.count(signature) != 1:
            raise SystemExit("expanded-bank right-span classifier is not unique")
        signature_offset = dispatcher.index(signature)
        right_span_address = 0x4380 + signature_offset + 5
        tail = dispatcher[signature_offset + 6:signature_offset + 9]
        if tail not in {bytes.fromhex("C3 00 43"), bytes.fromhex("C3 80 45")}:
            raise SystemExit("expanded-bank right span has an unknown publisher")
    else:
        right_span_bank = BANK
        right_span_address = 0x61A5
    if source_sha256 == R442_SHA:
        mutants = r442_mutants(source)
    elif source[0x77A8:0x77AC] == bytes.fromhex("CD 13 00 C9"):
        # Current r-series candidates route the shared tail through CALL
        # $0013; mutate the two native callers that still contain the old
        # visible-map repair, preserving the exact negative-control intent.
        mutants = {
            "forced-visible-menu-repair": patch_fixed_exact(
                patch_fixed_exact(
                    source, 0x1B72, bytes.fromhex("AF E0 E4 C9"),
                    bytes.fromhex("CD A0 42 C9")),
                0x1DCB, bytes.fromhex("AF E0 E4 C9"),
                bytes.fromhex("CD A0 42 C9")),
            "short-endpoint-span": patch_exact(
                source, 0x62D4, bytes([0x0B]), bytes([0x0A])),
            "missing-alternate-phase": patch_exact(
                source, 0x62CB, phase_target, bytes.fromhex("F6 61")),
            "short-right-endpoint-span": patch_exact(
                source, right_span_address, bytes([0x0A]), bytes([0x09]),
                bank=right_span_bank),
        }
    else:
        mutants = {
        "forced-visible-menu-repair": patch_fixed_exact(
            source, 0x77A8, bytes.fromhex("AF E0 E4 C9"),
            bytes.fromhex("CD A0 42 C9")),
        "short-endpoint-span": patch_exact(
            source, 0x62D4, bytes([0x0B]), bytes([0x0A])
        ),
        "missing-alternate-phase": patch_exact(
            source, 0x62CB, phase_target, bytes.fromhex("F6 61")
        ),
        "short-right-endpoint-span": patch_exact(
            source,
            right_span_address,
            bytes([0x0A]),
            bytes([0x09]),
            bank=right_span_bank,
        ),
        }
    results = {}
    for name, payload in mutants.items():
        mutant_path = output / f"{name}.gb"
        mutant_path.write_bytes(payload)
        try:
            replay = run_mutant(
                mutant_path, state, output / name, args.timeout,
                # Mutants intentionally change the candidate hash.  Keep the
                # authenticated source ROM available to the live observer so
                # its reviewed publisher contract remains bound while the
                # mutation itself is what the replay tests.
                mutation_base_rom=rom,
            )
        except RuntimeError as error:
            # A timeout rejects the run, but cannot establish route coverage
            # or visible detection of the intended mutation. Keep this
            # control failing until its actual evidence can be collected.
            if "live spike probe status=124" not in str(error):
                raise
            results[name] = {
                "rom": str(mutant_path),
                "rom_sha256": hashlib.sha256(payload).hexdigest(),
                "timeout_rejected": True,
                "route_valid": False,
                "visibly_rejected": False,
                "rejected": True,
                "passed": False,
                "summary": {"timeout_status": 124},
            }
            continue
        visibly_rejected = (
            replay["transient_mismatch_frames"] > 0
            or replay["inactive_preparation_mismatch_frames"] > 0
            or replay["rendered_wrong_palette0_tooth_cells"] > 0
            or replay["active_hazard_attr_write_hits"] > 0
            or replay["post_menu_active_hazard_attr_write_hits"] > 0
        )
        route_valid = (
            replay["menu_item_dispatch_hits"] >= 1
            and replay["menu_close_repair_hits"] >= 1
            and replay["menu_close_native_tail_hits"] >= 1
            and replay["low_health_forced_frames"] >= 120
        )
        rejected = not replay_is_clean(
            replay, close_frame=240, use_frame=80, low_health_frame=270
        )
        results[name] = {
            "rom": str(mutant_path),
            "rom_sha256": hashlib.sha256(payload).hexdigest(),
            "summary": stable_summary(replay),
            "route_valid": route_valid,
            "visibly_rejected": visibly_rejected,
            "rejected": rejected,
            "passed": route_valid and visibly_rejected and rejected,
        }

    checks = {
        "forced visible-map menu repair is caught": results[
            "forced-visible-menu-repair"
        ]["passed"],
        "short endpoint mutation is caught": results[
            "short-endpoint-span"
        ]["passed"],
        "alternate-phase mutation is caught": results[
            "missing-alternate-phase"
        ]["passed"],
        "right endpoint mutation is caught": results[
            "short-right-endpoint-span"
        ]["passed"],
    }
    receipt = {
        "schema": "penta-stage1-current-hazard-mutations-v1",
        "source_rom": str(rom),
        "source_sha256": source_sha256,
        "state": str(state),
        "state_sha256": digest(state),
        "mutants": results,
        "alternate_phase_route_preimage": phase_target.hex(" "),
        "right_endpoint_span": {
            "bank": right_span_bank,
            "address": f"0x{right_span_address:04X}",
        },
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
    print("PASS: all four Stage-1 hazard bug mutations are deterministically caught")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
