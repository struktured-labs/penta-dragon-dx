#!/usr/bin/env python3
"""Build the cycle-balanced r286 delta from exact Stage-4 r285.

r286 retains r285's Stage-4-only mapper entry, exact material continuation,
lazy non-Stage-4 departure, and untouched DAE9 router.  It makes installation
fail-closed by restoring DAB7/DAD5 before either WRAM copy, then adds exactly
64T to Stage-4 hits through a NOP/RET subroutine.  No non-Stage-4 transition
or steady-state instruction changes.

This static builder never imports or launches an emulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage4_lazy_departure_r285 as r285


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"

R285_SHA256 = "f93cbfd20760ec88363b039c47373422e90453116a841a872e22ef293d29ce75"
R285_RECEIPT_SHA256 = (
    "668b20cc7d4eb3954572e6002f6ee6cb94091ee56096cb61f64f848d51a76e74"
)
EXPECTED_CANDIDATE_SHA256 = (
    "a5521815ee25ca1c35a063198aec5f6a69609f99df7554201e41ab73699fc3c1"
)
EXPECTED_CHANGED_FROM_R285 = 72
EXPECTED_FUNCTIONAL_CHANGED_FROM_R285 = 70
EXPECTED_CHANGED_FROM_R281 = 150
EXPECTED_FUNCTIONAL_CHANGED_FROM_R281 = 148

INSTALLER_ADDR = r285.INSTALLER_ADDR
WRAM_PAYLOAD_ADDR = r285.WRAM_PAYLOAD_ADDR
TRAMPOLINE_PAYLOAD_ADDR = 0x633E
WRAM_BLOCK_ADDR = r285.WRAM_BLOCK_ADDR
WRAM_BLOCK_SIZE = 0x3E
DELAY_ADDR = 0xDB0D
GUARD_ADDR = r285.GUARD_ADDR
HELPER_ADDR = r285.HELPER_ADDR

RESTORER = r285.RESTORER
DELAY = bytes.fromhex("00 00 00 00 00 00 C9")
GUARD = r285.GUARD
HELPER = bytes.fromhex(
    "C5 D5 E5 AF E0 E0 7C EE CB 5F 16 DF "
    "21 F1 C1 46 24 4E CD 0D DB C3 92 DA"
)
TRAMPOLINE = r285.TRAMPOLINE


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_wram_block() -> bytes:
    block = bytearray(WRAM_BLOCK_SIZE)
    block[0:len(RESTORER)] = RESTORER
    delay_offset = DELAY_ADDR - WRAM_BLOCK_ADDR
    guard_offset = GUARD_ADDR - WRAM_BLOCK_ADDR
    helper_offset = HELPER_ADDR - WRAM_BLOCK_ADDR
    block[delay_offset:delay_offset + len(DELAY)] = DELAY
    block[guard_offset:guard_offset + len(GUARD)] = GUARD
    block[helper_offset:helper_offset + len(HELPER)] = HELPER
    require(WRAM_BLOCK_ADDR + len(RESTORER) == DELAY_ADDR,
            "delay no longer follows restorer")
    require(DELAY == bytes(6) + bytes((0xC9,)),
            "delay body is not six NOPs plus RET")
    require(GUARD_ADDR + len(GUARD) == HELPER_ADDR,
            "Stage4 guard no longer falls through to helper")
    require(GUARD_ADDR + len(GUARD) + int.from_bytes(
        GUARD[-1:], "little", signed=True
    ) == WRAM_BLOCK_ADDR, "non-Stage4 guard no longer reaches DB00")
    require(HELPER[-6:] == bytes.fromhex("CD 0D DB C3 92 DA"),
            "helper delay/join sequence changed")
    require(HELPER_ADDR + len(HELPER) == WRAM_BLOCK_ADDR + WRAM_BLOCK_SIZE,
            "helper no longer ends exactly at DB3D")
    return bytes(block)


def build_installer() -> bytes:
    code = bytes([
        # A previous Stage7 arm or partially installed r285 state must become
        # native before either copy can be observed by an interrupt/callback.
        0x3E, 0xEB,
        0xEA, r285.RUNTIME_REDIRECT_OPERAND_ADDR & 0xFF,
        r285.RUNTIME_REDIRECT_OPERAND_ADDR >> 8,
        0x3E, 0x60,
        0xEA, r285.RUNTIME_LANDING_OPERAND_ADDR & 0xFF,
        r285.RUNTIME_LANDING_OPERAND_ADDR >> 8,
        0xC5, 0xD5,                         # preserve BC (especially C), DE
        0x21, WRAM_PAYLOAD_ADDR & 0xFF, WRAM_PAYLOAD_ADDR >> 8,
        0x11, WRAM_BLOCK_ADDR & 0xFF, WRAM_BLOCK_ADDR >> 8,
        0x01, WRAM_BLOCK_SIZE, 0x00,
        0xCD, 0xB3, 0x09,
        0x21, TRAMPOLINE_PAYLOAD_ADDR & 0xFF,
        TRAMPOLINE_PAYLOAD_ADDR >> 8,
        0x11, r285.TRAMPOLINE_ADDR & 0xFF, r285.TRAMPOLINE_ADDR >> 8,
        0x01, len(TRAMPOLINE), 0x00,
        0xCD, 0xB3, 0x09,
        0x3E, r285.TRAMPOLINE_ADDR & 0xFF,
        0xEA, r285.RUNTIME_LANDING_OPERAND_ADDR & 0xFF,
        r285.RUNTIME_LANDING_OPERAND_ADDR >> 8,  # final DAD5=$5D commit
        0xD1, 0xC1,
        0xF1,                               # saved original bank/DEC flags
        0x21, r285.STAGE4_MATERIAL_CONT_ADDR & 0xFF,
        r285.STAGE4_MATERIAL_CONT_ADDR >> 8,
        0xE5,
        0x21, r285.STAGE4_A_STUB_ADDR & 0xFF,
        r285.STAGE4_A_STUB_ADDR >> 8,
        0xE5,
        0x21, 0x01, 0xC6,
        0x06, 0x08,
        0xC3, 0x61, 0x00,
    ])
    native_redirect = bytes.fromhex("3E EB EA B7 DA")
    native_landing = bytes.fromhex("3E 60 EA D5 DA")
    fast_commit = bytes.fromhex("3E 5D EA D5 DA")
    require(code.startswith(native_redirect + native_landing),
            "installer is not fail-closed from its first instruction")
    require(code.count(native_redirect) == 1,
            "DAB7 native reset is not unique")
    require(code.count(native_landing) == 1,
            "DAD5 native reset is not unique")
    require(code.count(fast_commit) == 1,
            "DAD5 fast commit is not unique")
    require(code.rfind(fast_commit) > code.rfind(bytes.fromhex("CD B3 09")),
            "fast landing becomes reachable before the final copy")
    return code


def patch_exact(rom: bytearray, bank: int, address: int, expected: bytes,
                replacement: bytes, label: str, allowed: set[int]) -> None:
    require(len(expected) == len(replacement), f"{label} width changed")
    offset = r285.bank_offset(bank, address)
    actual = bytes(rom[offset:offset + len(expected)])
    require(actual == expected,
            f"{label} preimage moved: {actual.hex(' ')} != {expected.hex(' ')}")
    rom[offset:offset + len(replacement)] = replacement
    allowed.update(range(offset, offset + len(replacement)))


def construct(base: bytes, r281_bytes: bytes, r279_bytes: bytes
              ) -> tuple[bytes, dict[str, object]]:
    """Emit the balanced repair with generated references, not corpus claims."""
    require(digest(base) == R285_SHA256, f"wrong r285 base: {digest(base)}")
    regenerated, r285_receipt = r285.construct(r281_bytes, r279_bytes)
    require(regenerated == base, "r285 base does not regenerate byte-exactly")
    require(r285_receipt["candidate_sha256"] == R285_SHA256,
            "r285 lineage receipt changed")

    old_installer = r285.build_installer()
    new_installer = build_installer()
    require(len(new_installer) >= len(old_installer),
            "unexpected installer shrink")
    installer_width = len(new_installer)
    old_installer_region = old_installer + bytes([0xFF]) * (
        installer_width - len(old_installer)
    )

    old_payload_region = (
        r285.build_wram_block() + r285.TRAMPOLINE + bytes([0xFF]) * 2
    )
    new_block = build_wram_block()
    new_payload_region = new_block + TRAMPOLINE
    require(len(old_payload_region) == len(new_payload_region) == 0x41,
            "payload delta width changed")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    patch_exact(
        rom, r285.OVERLAY_BANK, INSTALLER_ADDR,
        old_installer_region, new_installer,
        "r286 fail-closed installer", allowed,
    )
    patch_exact(
        rom, r285.OVERLAY_BANK, WRAM_PAYLOAD_ADDR,
        old_payload_region, new_payload_region,
        "r286 padded WRAM payload", allowed,
    )
    r285.update_checksums(rom)
    candidate = bytes(rom)

    changed_from_r285 = {
        index for index, (before, after) in enumerate(zip(base, candidate, strict=True))
        if before != after
    }
    require(changed_from_r285 <= allowed,
            f"r286 escaped delta-owned bytes: {sorted(changed_from_r285 - allowed)[:8]}")
    changed_from_r281 = {
        index for index, (before, after) in enumerate(
            zip(r281_bytes, candidate, strict=True)
        ) if before != after
    }
    functional_r285 = changed_from_r285 - {0x014D, 0x014E, 0x014F}
    functional_r281 = changed_from_r281 - {0x014D, 0x014E, 0x014F}
    if EXPECTED_CHANGED_FROM_R285 >= 0:
        require(len(changed_from_r285) == EXPECTED_CHANGED_FROM_R285,
                f"r285 delta count drifted: {len(changed_from_r285)}")
        require(len(functional_r285) == EXPECTED_FUNCTIONAL_CHANGED_FROM_R285,
                f"r285 functional delta drifted: {len(functional_r285)}")
        require(len(changed_from_r281) == EXPECTED_CHANGED_FROM_R281,
                f"r281 delta count drifted: {len(changed_from_r281)}")
        require(len(functional_r281) == EXPECTED_FUNCTIONAL_CHANGED_FROM_R281,
                f"r281 functional delta drifted: {len(functional_r281)}")

    # All original-bank bytes, r281 runtime sources, transition selector,
    # DAE9 router, r281 palette delta, and the r279 Stage7 code stay exact r285.
    for bank in r285.MIRROR_BANKS:
        require(r285.region(candidate, bank, 0x4000, 0x4000)
                == r285.region(base, bank, 0x4000, 0x4000),
                f"r286 changed original bank{bank}")
    require(r285.region(candidate, r285.OVERLAY_BANK, 0x6C80, 0x5C5)
            == r285.region(base, r285.OVERLAY_BANK, 0x6C80, 0x5C5),
            "r286 changed existing Stage7 helper/lazy-disarm")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")

    # Parent/north convention excludes a common 4T boundary instruction from
    # both absolute paths.  The delta and all externally relevant savings are
    # identical under either convention.
    native_t = 272
    r285_fast_t = 180
    delay_t = 24 + 6 * 4 + 16
    r286_fast_t = r285_fast_t + delay_t
    require((delay_t, r286_fast_t, native_t - r286_fast_t) == (64, 244, 28),
            "r286 Stage4 cycle contract changed")
    departure_nonzero_t = 384
    departure_zero_t = 372
    require(departure_nonzero_t - native_t == 112,
            "lazy nonzero departure overhead changed")

    receipt = {
        "schema": "penta-stage4-lazy-departure-r286-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "emulator_invoked": False,
        "r281_sha256": r285.R281_SHA256,
        "r285_base_sha256": R285_SHA256,
        "candidate_sha256": candidate_sha,
        "changed_from_r285_including_checksums": len(changed_from_r285),
        "functional_changed_from_r285": len(functional_r285),
        "changed_from_r281_including_checksums": len(changed_from_r281),
        "functional_changed_from_r281": len(functional_r281),
        "checksums": r285.checksum_contract(candidate),
        "regions": [
            {
                "range": f"bank22:${INSTALLER_ADDR:04X}-${INSTALLER_ADDR + len(new_installer) - 1:04X}",
                "length": len(new_installer),
                "sha256": digest(new_installer),
                "purpose": "fail-closed Stage4 installer",
            },
            {
                "range": "$DB00-$DB3D (payload bank22:$6300-$633D)",
                "length": len(new_block),
                "sha256": digest(new_block),
                "purpose": "lazy restorer, 64T delay, guard, page-pair helper",
            },
            {
                "range": "bank22:$633E-$6340 -> WRAM $DA5D-$DA5F",
                "length": len(TRAMPOLINE),
                "sha256": digest(TRAMPOLINE),
                "purpose": "JP $DB20 trampoline",
            },
        ],
        "atomic_contract": [
            "installer instruction 1 begins DAB7=$EB reset",
            "installer next writes DAD5=$60 before either memcpy",
            "copy complete DB00-DB3D block",
            "copy complete DA5D-DA5F trampoline",
            "commit DAD5=$5D only after both copies",
        ],
        "cycle_contract_t": {
            "native_nonzero_to_shared_compare": native_t,
            "r285_fast_to_shared_compare": r285_fast_t,
            "delay_CALL": 24,
            "delay_6_NOP": 24,
            "delay_RET": 16,
            "added_per_Stage4_hit": delay_t,
            "r286_fast_to_shared_compare": r286_fast_t,
            "r286_saved_per_Stage4_hit": native_t - r286_fast_t,
            "first_nonstage_nonzero_total": departure_nonzero_t,
            "first_nonstage_zero_total": departure_zero_t,
            "one_time_departure_overhead": 112,
        },
        "transferred_r285_contracts": {
            "original_Stage4_entry_and_exact_material_continuation": True,
            "original_nonstage_transition_selector_and_timing": True,
            "DAD4_normalized_A_lazy_recompute": True,
            "DAE9_router_never_modified": True,
            "Stage7_arm_helper_and_gameplay_bytes_exact": True,
            "r281_six_byte_visual_delta": r285_receipt["lineage"]["r281_delta_offsets"],
        },
        "required_live_gates": [
            "Stage4 strict speed must fall within 0.99-1.01",
            "Stage4 semantic/room-edge and SELECT-menu containment",
            "Stage4->5->6->7 plus title/Stage1 DB00-DB3D lifecycle",
            "Stage5/Stage7 strict phase containment",
            "Crystal and candidate-bound visual aggregate",
        ],
    }
    return candidate, receipt


def install(base: bytes, r281_bytes: bytes, r279_bytes: bytes,
            r285_receipt_bytes: bytes, *, evidence: dict[str, bytes] | None = None
            ) -> tuple[bytes, dict[str, object]]:
    require(digest(base) == R285_SHA256, f"wrong r285 base: {digest(base)}")
    require(digest(r285_receipt_bytes) == R285_RECEIPT_SHA256,
            "r285 build receipt identity changed")
    regenerated, history = r285.install(r281_bytes, r279_bytes, evidence=evidence)
    require(regenerated == base, "r285 base does not regenerate byte-exactly")
    require(history["candidate_sha256"] == R285_SHA256, "r285 lineage receipt changed")
    candidate, construction = construct(base, r281_bytes, r279_bytes)
    receipt = {}
    for key, value in construction.items():
        if key in ("historical_evidence_consumed", "fresh_live_qualification"):
            continue
        if key == "schema":
            value = "penta-stage4-lazy-departure-r286-build-v1"
        elif key == "status":
            value = "STATIC_PASS_LIVE_GATES_REQUIRED"
        elif key == "candidate_sha256":
            receipt["r285_build_receipt_sha256"] = R285_RECEIPT_SHA256
        elif key == "cycle_contract_t":
            historical_cycles = {}
            for name, metric in value.items():
                historical_cycles[name] = metric
                if name == "r286_saved_per_Stage4_hit":
                    historical_cycles["r279_bound_decisions"] = 985
                    historical_cycles["projected_saving"] = metric * 985
            value = historical_cycles
        elif key == "transferred_r285_contracts":
            value = dict(value)
            visual_delta = value.pop("r281_six_byte_visual_delta")
            value["C1F1_C2F1_bound_corpora"] = history["corpus_contract"]
            value["DB00_DB7F_current_r281_all_stage_ownership"] = history["wram_ownership"]
            value["r281_six_byte_visual_delta"] = visual_delta
        elif key == "required_live_gates":
            receipt["r286_wram_ownership"] = {
                "owned_subrange": "$DB00-$DB3D",
                "owned_subrange_size": WRAM_BLOCK_SIZE,
                "bound_snapshot_range": "$DB00-$DB7F",
                "bound_snapshot_sha256": r285.WRAM_OWNERSHIP_SHA256,
                "bound_current_r281_stages": sorted(r285.WRAM_META),
                "scope_limit": (
                    "Stage2-7 snapshots prove the larger range was zero at each "
                    "capture; title/Stage1/menu/transition lifetime remains a "
                    "required live gate"
                ),
            }
        receipt[key] = value
    return candidate, receipt


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved == scratch or scratch in resolved.parents,
            f"output must remain below {scratch}: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path,
                        default=TMP / "stage4-lazy-departure-r285/candidate.gb")
    parser.add_argument("--r285-receipt", type=Path,
                        default=TMP / "stage4-lazy-departure-r285/build-receipt.json")
    parser.add_argument("--r281", type=Path,
                        default=TMP / "stage1-metallic-teeth-r281/candidate.gb")
    parser.add_argument("--r279", type=Path,
                        default=TMP / "stage7-lazy-disarm-r279/candidate.gb")
    parser.add_argument("--output", type=Path,
                        default=TMP / "stage4-lazy-departure-r286/candidate.gb")
    parser.add_argument("--receipt", type=Path,
                        default=TMP / "stage4-lazy-departure-r286/build-receipt.json")
    args = parser.parse_args()
    output = require_tmp(args.output)
    receipt_path = require_tmp(args.receipt)
    candidate, receipt = install(
        args.base.read_bytes(), args.r281.read_bytes(), args.r279.read_bytes(),
        args.r285_receipt.read_bytes(),
    )
    for path, payload in (
        (output, candidate),
        (receipt_path, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
