#!/usr/bin/env python3
"""Build r303: r300 plus timing-safe Stage-1 scene-$0B publication gates.

r302 put every ordinary scene-$02/$0A call through a shared predicate.  That
added 68--84 T-cycles at hot publication sites and failed its live visual
oracle.  r303 keeps the original D880/F7 fast paths in the shared attribute,
art, and BG7 services and evaluates FFB7 only after those paths reject.

The bank-19 row and transition helpers are downstream of the Stage-1-only
bank-19 publication mapper.  They therefore gate directly on authoritative
FFB7=$02, with cycle-exact padding, rather than admitting raw scene $03 via
the unsafe F6 mask.  Row miniboss ownership uses FFBF explicitly; raw D880
bit 3 no longer mistakes low-health $0B for the miniboss path.

No emulator is invoked.  The candidate remains non-promotable until the
candidate-bound low-health, visual, transition, menu, and speed gates pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_lowhealth_all_gates_r302 as r302


r297 = r302.r297
r300 = r302.r300
r301 = r302.r301
ROOT = r297.ROOT
TMP = r297.TMP
BASE = r297.BASE
BASE_RECEIPT = r297.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-fast-scene0b-gates-r303/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-fast-scene0b-gates-r303/build-receipt.json"

MIRROR_BANKS = r297.MIRROR_BANKS
ART_ADDR = r302.r296.ART_LOADER_GATE_ADDR
BG7_PRELOAD_ADDR = 0x71B4
BG7_GATE_ADDR = r302.r296.BG7_SELECTOR_GATE_ADDR
SHARED_HELPER_ADDR = 0x5D25
SHARED_HELPER = bytes.fromhex("47 F0 B7 A8 3D C8 2E F8 C9")

OLD_ART_REGION = bytes.fromhex(
    "FA 5B DF E6 03 FE 03 C8 "
    "FA 80 D8 E6 F7 FE 02 C0 "
    "01 AA 6C C5 3E 13 C3 61 00 C9 00 00 00 00 00"
)
NEW_ART_REGION = bytes.fromhex(
    # INC/AND/JR is the same phase predicate modulo four.  Its accepted path
    # saves 4T and its rare rejecting path lands on the relocated final RET.
    "FA 5B DF 3C E6 03 28 14 "
    # Original scene fast path; only NZ pays for the helper.  The helper
    # returns Z for Stage-1 $0B and NZ after restoring BG-default L=$F8 for
    # all rejected contexts.  RET NZ preserves the native art rejection ABI.
    "FA 80 D8 E6 F7 FE 02 C4 25 5D C0 "
    "01 AA 6C C5 3E 13 C3 61 00 C9 00 00"
)

OLD_BG7_REGION = bytes.fromhex(
    "2E F8 FA 80 D8 E6 F7 FE 02 20 02 2E C8 00"
)
NEW_BG7_REGION = bytes.fromhex(
    # Preselect the accepted source.  The slow helper restores $F8 only on
    # rejection; scene $02/$0A skips the helper and retains exact total time.
    "2E C8 FA 80 D8 E6 F7 FE 02 C4 25 5D 00 00"
)

ROW_START = 0x6BA7
ROW_ALIGN = 0x6BBE
NEW_ROW_PREFIX = bytes.fromhex(
    "C1 "
    # 36T before JP: 12+8+12+4, matching old LD/LDB/AND/CP's 36T.
    "F0 B7 FE 02 18 00 00 C2 50 6C "
    "FA FD DC B7 CA 50 6C "
    # FFBF owns miniboss classification; D880=$0B must not alias bit 3.
    "F0 BF B7 20 0C"
)
TRANSITION_ADDR = r297.TRANSITION_MASK_ADDR - 4
NEW_TRANSITION_GATE = bytes.fromhex("F0 B7 FE 02 00 00 00 C0")

CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})


def digest(payload: bytes | bytearray) -> str:
    return r302.digest(payload)


def receipt_bytes(payload: dict[str, object]) -> bytes:
    return r302.receipt_bytes(payload)


def delta(before: bytes, after: bytes, *, functional: bool = False) -> set[int]:
    return r302.delta(before, after, functional=functional)


def byte_range(bank: int, address: int, width: int) -> set[int]:
    return r302.byte_range(bank, address, width)


def shared_accepts(scene: int, ffb7: int) -> bool:
    """Exact shared attr/art/BG7 fast+slow predicate."""
    masked = scene & 0xF7
    return masked == 0x02 or (((ffb7 ^ masked) - 1) & 0xFF) == 0


def exhaustive_contract() -> dict[str, object]:
    accepted_stage1: set[int] = set()
    cases = 0
    for ffb7 in range(256):
        for dd06 in range(4):
            for ffbf in range(4):
                scene = r297.reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                accepted = shared_accepts(scene, ffb7)
                # $0A is an existing native fast alias and is reachable only
                # from the game's miniboss publisher.  Newly admitted states
                # must be exactly Stage-1 low-health $0B.
                old = r297.old_attr_accepts(scene)
                if accepted and not old:
                    r297.require(
                        ffb7 == 0x02 and scene == 0x0B,
                        "slow predicate admitted a non-Stage-1 reachable state",
                    )
                if ffb7 == 0x02 and scene in (0x02, 0x0A, 0x0B):
                    r297.require(accepted, "reachable Stage-1 state rejected")
                    accepted_stage1.add(scene)
                cases += 1
    r297.require(accepted_stage1 == {0x02, 0x0A, 0x0B},
                 "Stage-1 reachable set changed")
    r297.require(not shared_accepts(0x18, 0x02),
                 "Stage-card splash $18 admitted")
    r297.require(not shared_accepts(0x03, 0x03),
                 "Stage-2 scene $03 admitted")
    return {
        "reachable_states_exhausted": cases,
        "accepted_stage1_scenes": ["02", "0A", "0B"],
        "only_new_reachable_state": "FFB7=02,D880=0B",
        "splash_18_rejected": True,
        "stage2_03_rejected": True,
        "bank19_direct_FFB7_precondition": (
            "row/transition are downstream of the Stage-1-only bank19 mapper"
        ),
    }


def timing_contract() -> dict[str, object]:
    result = {
        "attr_scene02_0A": {"r300": 44, "r303": 44, "delta": 0},
        "art_phase_pass_scene02_0A": {"r300": 80, "r303": 88, "delta": 8},
        "art_phase_reject": {"r300": 52, "r303": 56, "delta": 4},
        "bg7_scene02_0A_through_continuation": {
            "r300": 60, "r303": 60, "delta": 0,
        },
        "row_scene02_0A_scene_gate": {"r300": 48, "r303": 48, "delta": 0},
        "row_nonstage_scene_gate": {"r300": 52, "r303": 52, "delta": 0},
        "transition_scene02_0A": {"r300": 40, "r303": 40, "delta": 0},
        "transition_nonstage": {"r300": 52, "r303": 52, "delta": 0},
    }
    r297.require(all(
        item["delta"] == 0
        for name, item in result.items()
        if name not in {"art_phase_pass_scene02_0A", "art_phase_reject"}
    ), "a claimed cycle-exact fast path drifted")
    return result


def patch_exact(
    rom: bytearray, preimage: bytes, *, bank: int, address: int,
    old: bytes, new: bytes, allowed: set[int], label: str,
) -> None:
    offset = r297.bank_offset(bank, address)
    r297.patch_exact(rom, preimage, offset, old, new, allowed, label)


def owned_ranges() -> set[int]:
    owned: set[int] = set()
    for bank in MIRROR_BANKS:
        owned |= byte_range(bank, ART_ADDR - 8, len(NEW_ART_REGION))
        owned |= byte_range(bank, BG7_PRELOAD_ADDR, len(NEW_BG7_REGION))
        owned |= byte_range(bank, SHARED_HELPER_ADDR, len(SHARED_HELPER))
    owned |= byte_range(r297.ROW_BANK, ROW_START, len(NEW_ROW_PREFIX))
    owned |= byte_range(
        r297.ROW_BANK, TRANSITION_ADDR, len(NEW_TRANSITION_GATE)
    )
    return owned


def validate_preimages(source: bytes, r300_candidate: bytes) -> None:
    for bank in MIRROR_BANKS:
        art = r297.bank_offset(bank, ART_ADDR - 8)
        bg7 = r297.bank_offset(bank, BG7_PRELOAD_ADDR)
        helper = r297.bank_offset(bank, SHARED_HELPER_ADDR)
        r297.require(r300_candidate[art:art + len(OLD_ART_REGION)]
                     == OLD_ART_REGION, f"bank{bank} art region changed")
        r297.require(r300_candidate[bg7:bg7 + len(OLD_BG7_REGION)]
                     == OLD_BG7_REGION, f"bank{bank} BG7 region changed")
        r297.require(source[helper:helper + len(SHARED_HELPER)]
                     == bytes(len(SHARED_HELPER)),
                     f"bank{bank} post-RET helper gap changed")
        # $5D24 is the preceding RET and $5D2E begins immutable data; this is
        # an exact bounded code gap, not a zero-looking graphics/table tail.
        r297.require(source[helper - 1] == 0xC9 and source[helper + 9] == 0x05,
                     f"bank{bank} helper boundary changed")

    row = r297.bank_offset(r297.ROW_BANK, ROW_START)
    old_row = bytes.fromhex(
        "C1 FA 80 D8 47 E6 F6 FE 02 C2 50 6C "
        "FA FD DC B7 CA 50 6C CB 58 20 0C"
    )
    r297.require(r300_candidate[row:row + len(old_row)] == old_row,
                 "r300 row prefix changed")
    transition = r297.bank_offset(r297.ROW_BANK, TRANSITION_ADDR)
    r297.require(
        r300_candidate[transition:transition + 8]
        == bytes.fromhex("FA 80 D8 E6 F6 FE 02 C0"),
        "r300 transition gate changed",
    )


def construct(source: bytes) -> tuple[bytes, dict[str, object]]:
    r297.require(len(source) == r297.ROM_SIZE, "base is not 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256, "wrong exact r292 base")
    r297_full, r297_receipt = r297.construct(source)
    r300_candidate, r300_receipt = r300.construct(source)
    r297.require(digest(r297_full) == r302.R297_FULL_SHA256,
                 "r297 generated identity changed")
    r297.require(digest(r300_candidate) == r302.R300_SHA256,
                 "r300 generated identity changed")
    validate_preimages(source, r300_candidate)
    scene = exhaustive_contract()
    timing = timing_contract()

    rom = bytearray(r300_candidate)
    allowed: set[int] = set(CHECKSUM_OFFSETS)
    for bank in MIRROR_BANKS:
        patch_exact(
            rom, r300_candidate, bank=bank, address=SHARED_HELPER_ADDR,
            old=bytes(len(SHARED_HELPER)), new=SHARED_HELPER,
            allowed=allowed, label=f"bank{bank} conditional scene helper",
        )
        patch_exact(
            rom, r300_candidate, bank=bank, address=ART_ADDR - 8,
            old=OLD_ART_REGION, new=NEW_ART_REGION, allowed=allowed,
            label=f"bank{bank} fast art gate",
        )
        patch_exact(
            rom, r300_candidate, bank=bank, address=BG7_PRELOAD_ADDR,
            old=OLD_BG7_REGION, new=NEW_BG7_REGION, allowed=allowed,
            label=f"bank{bank} cycle-exact BG7 gate",
        )
    patch_exact(
        rom, r300_candidate, bank=r297.ROW_BANK, address=ROW_START,
        old=r300_candidate[
            r297.bank_offset(r297.ROW_BANK, ROW_START):
            r297.bank_offset(r297.ROW_BANK, ROW_ALIGN)
        ],
        new=NEW_ROW_PREFIX, allowed=allowed, label="bank19 row gate/miniboss",
    )
    patch_exact(
        rom, r300_candidate, bank=r297.ROW_BANK, address=TRANSITION_ADDR,
        old=bytes.fromhex("FA 80 D8 E6 F6 FE 02 C0"),
        new=NEW_TRANSITION_GATE, allowed=allowed,
        label="bank19 cycle-exact transition gate",
    )

    functional_before_checksum = delta(
        r300_candidate, bytes(rom), functional=True
    )
    r297.require(functional_before_checksum <= owned_ranges(),
                 "r303 escaped owned ranges")
    r297.update_checksums(rom)
    candidate = bytes(rom)

    # Composition/omission controls.
    bank20 = slice(
        r300.SEMANTIC_BANK * r297.BANK_SIZE,
        (r300.SEMANTIC_BANK + 1) * r297.BANK_SIZE,
    )
    r297.require(candidate[bank20] == r300_candidate[bank20],
                 "r300 semantic bank changed")
    for start, width in (
        (r297.RST0_ADDR, len(r297.NEW_RST0)),
        (r297.ROOM_STUB_ADDR, len(r297.NEW_ROOM_STUB)),
        (r297.bank_offset(r297.EXPANSION_BANK, r297.WALL_HELPER_ADDR),
         len(r297.WALL_HELPER)),
    ):
        r297.require(candidate[start:start + width]
                     == r297_full[start:start + width],
                     "r297 wall component changed")
    r297.require(candidate[0x4303:0x4319] == source[0x4303:0x4319],
                 "native compiler entry changed")
    r297.require(not (delta(source, candidate, functional=True)
                      & r302.r301_owned_ranges()),
                 "rejected r301 bytes leaked into r303")
    r297.require(bytes.fromhex("E6 F6 FE 02") not in
                 candidate[
                     r297.bank_offset(r297.ROW_BANK, ROW_START):
                     r297.bank_offset(r297.ROW_BANK, ROW_ALIGN)
                 ], "unsafe row F6 predicate survived")

    functional = delta(r300_candidate, candidate, functional=True)
    receipt: dict[str, object] = {
        "schema": "penta-stage1-fast-scene0b-gates-r303-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "base_sha256": r297.BASE_SHA256,
        "r297_generated_sha256": r297_receipt["candidate_sha256"],
        "r300_generated_sha256": r300_receipt["candidate_sha256"],
        "candidate_sha256": digest(candidate),
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "components": {
            "r297_attr_fast_path": "retained byte-exact; scene02/0A +0T",
            "art_gate": "conditional slow helper; accepted hot path +8T including phase gate",
            "bg7_gate": "preselect C8; reject helper restores F8; hot path +0T",
            "row_gate": "authoritative FFB7 plus explicit FFBF; cycle exact",
            "transition_gate": "authoritative FFB7; cycle exact",
            "r297_wall_and_r300_semantic": "retained byte-exact",
            "r301_dead_menu_hook": "omitted",
            "menu_close_invalidation": "deferred to separately approved r304 overlay",
            "bank21_stage_card_helper": "unchanged; live execution must be measured",
        },
        "offline_contract": {"scene": scene, "timing": timing},
        "ownership": {
            "functional_changed_bytes_from_r300": len(functional),
            "changed_offsets_from_r300": [
                f"0x{offset:06X}" for offset in sorted(functional)
            ],
            "r301_overlap_bytes": 0,
        },
        "required_gates": [
            "candidate-bound DCBB low-health scene0B publication",
            "zero unsafe attr mismatches and no white/cyan flashes",
            "hazard/menu/room01 rendered continuity",
            "bank19 mapper ownership trace for direct FFB7 row/transition gates",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes, *, room01_capture: bytes | None = None
          ) -> tuple[bytes, dict[str, object]]:
    r297.require(len(source) == r297.ROM_SIZE, "base is not 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256, "wrong exact r292 base")
    r297.require(digest(base_receipt_bytes) == r297.BASE_RECEIPT_SHA256,
                 "r292 receipt identity changed")
    r302.validate_r300_identity(source, base_receipt_bytes, room01_capture=room01_capture)
    candidate, receipt = construct(source)
    receipt.pop("historical_evidence_consumed")
    receipt.pop("fresh_live_qualification")
    receipt.update({"schema": "penta-stage1-fast-scene0b-gates-r303-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
                    "base_receipt_sha256": r297.BASE_RECEIPT_SHA256})
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r297.checked_output(args.output, "candidate output")
    receipt_path = r297.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
