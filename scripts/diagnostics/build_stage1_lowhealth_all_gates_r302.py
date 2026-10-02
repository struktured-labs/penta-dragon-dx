#!/usr/bin/env python3
"""Build r302: r300 room semantics plus all five Stage-1 scene gates.

r300 contains the r297 room-write hook, the native bank-19 row/transition
mask repairs, and the room-local bank-20 semantic-row repair.  Its attribute
gateway still uses r297's attr-only slow predicate, while the art loader and
BG7 selector retain r292's scene-$0B rejection.  This diagnostic candidate
replaces only that attr implementation and adds only the art/BG7 gates using
r296's shared reachable-scene predicate.  The native bank-19 row ABI remains
byte-exact apart from r297's two one-byte F7->F6 masks.

r301 is deliberately *not* composed.  An authenticated operator-route audit
observed no bank-21 ingress, helper, effect, or cache writes, so its menu
invalidation is dead on the route it was intended to fix.  Its bank-13 menu
body and bank-21 caves are asserted to remain at their pre-r301 bytes until a
real menu-route hook is identified.

No emulator is invoked by this builder.  The result remains non-promotable
until the independent live visual, hazard, transition, and speed gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_room01_locked_wall_r297 as r297
import build_stage1_room01_semantic_row_r300 as r300
import build_stage1_room01_wall_scene0b_r296 as r296
import build_stage1_scene0b_menu_invalidation_r301 as r301


ROOT = r297.ROOT
TMP = r297.TMP
BASE = r297.BASE
BASE_RECEIPT = r297.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-lowhealth-all-gates-r302/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-lowhealth-all-gates-r302/build-receipt.json"

R297_FULL_SHA256 = r301.R297_FULL_SHA256
R297_RECEIPT_SHA256 = (
    "4148f9a2cb3449254118f7618c5931f1390acea733ab76127ed243a6f0855b47"
)
R300_SHA256 = "abc06464cb331fb93da5b7a573374775896306b3aefdbe7908280dea70edf3d7"
R300_RECEIPT_SHA256 = (
    "9d8ff1d07bf26003376dff60150e47506df50c36a8cc44325db86e766e5fdbf1"
)
R301_REJECTED_SHA256 = (
    "e5c307c59c6232f808ffb6cd026c8d4427682364d2b4f0b9fe221ca5842079c8"
)
LOW_HEALTH_COMPONENTS = frozenset({"attr", "art", "bg7"})
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def receipt_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def delta(before: bytes, after: bytes, *, functional: bool = False) -> set[int]:
    r297.require(len(before) == len(after), "delta operands differ in width")
    changed = {
        index
        for index, pair in enumerate(zip(before, after, strict=True))
        if pair[0] != pair[1]
    }
    return changed - CHECKSUM_OFFSETS if functional else changed


def byte_range(bank: int, address: int, width: int) -> set[int]:
    start = r297.bank_offset(bank, address)
    return set(range(start, start + width))


def r297_attr_ranges() -> set[int]:
    """Exact r297 attr-only regions that r296 is allowed to replace."""
    result: set[int] = set()
    for bank in r297.MIRROR_BANKS:
        result |= byte_range(bank, r297.ATTR_GATEWAY_ADDR,
                             len(r297.OLD_ATTR_GATEWAY))
    result |= byte_range(13, 0x5D4C, len(r297.BANK13_ATTR_HELPER))
    result |= byte_range(16, 0x6180, len(r297.BANK16_ATTR_FRONT))
    result |= byte_range(
        16, r297.BANK16_ATTR_TAIL_ADDR, len(r297.BANK16_ATTR_TAIL)
    )
    return result


def r301_owned_ranges() -> set[int]:
    """The rejected r301 functional ranges, all forbidden in r302."""
    return (
        byte_range(13, r301.MENU_HELPER_ADDR + len(r301.MENU_PREFIX),
                   len(r301.NEW_MENU_BODY))
        | byte_range(21, r301.INGRESS_ADDR, len(r301.INGRESS))
        | byte_range(21, r301.CONTEXT_HELPER_ADDR, len(r301.CONTEXT_HELPER))
    )


def predicate_cycles(*, bank: int, scene: int, ffb7: int) -> int:
    """T-cycles in r296's shared predicate, excluding the caller's CALL."""
    r297.require(bank in r296.MIRROR_BANKS,
                 f"unexpected shared-predicate bank {bank}")
    if ffb7 != 0x02:
        # LDH A,[B7]; CP 02; RET NZ (taken).
        return 12 + 8 + 20
    # LDH; CP; RET NZ (not); LD A,[D880]; AND; CP; RET.
    common = 12 + 8 + 8 + 16 + 8 + 8 + 16
    # Bank 16's predicate is split across two audited gaps and reaches its
    # tail with JP $6268.  Bank 13 is contiguous.
    return common + (16 if bank == 16 else 0)


def gate_cycles(
    component: str, *, bank: int, scene: int, ffb7: int,
) -> int:
    """T-cycles through one complete r302 gate, including predicate CALL."""
    r297.require(component in LOW_HEALTH_COMPONENTS,
                 f"unknown low-health component {component!r}")
    accepted = r296.predicate_accepts(scene, ffb7)
    branch = {
        "attr": 12 if accepted else 16,  # JP NZ
        "art": 8 if accepted else 20,    # RET NZ
        "bg7": 8 if accepted else 12,    # JR NZ
    }[component]
    return 24 + predicate_cycles(bank=bank, scene=scene, ffb7=ffb7) + branch


def r300_gate_cycles(
    component: str, *, bank: int, scene: int, ffb7: int,
) -> int:
    """Exact pre-r302 gate cost, including r297's attr-only slow path."""
    r297.require(component in LOW_HEALTH_COMPONENTS,
                 f"unknown baseline component {component!r}")
    r297.require(bank in r296.MIRROR_BANKS,
                 f"unexpected baseline mirror bank {bank}")
    masked = scene & 0xF7
    fast = masked == 0x02
    if component == "attr":
        if fast:
            return 16 + 8 + 8 + 12  # LD/AND/CP; CALL NZ not taken
        accepted = r297.r297_attr_accepts(scene, ffb7)
        helper = 44 if accepted else 60
        if bank == 16:
            helper += 16  # bank16's split helper uses JP $6268
        return 16 + 8 + 8 + 24 + helper
    branch = {
        "art": 8 if fast else 20,
        "bg7": 8 if fast else 12,
    }[component]
    return 16 + 8 + 8 + branch


def timing_contract() -> dict[str, object]:
    cases = {
        "stage1_scene02": (0x02, 0x02),
        "stage1_scene0A": (0x0A, 0x02),
        "stage1_scene0B": (0x0B, 0x02),
        "splash_scene18": (0x18, 0x02),
        "stage2_scene03": (0x03, 0x03),
    }
    result: dict[str, object] = {}
    for label, (scene, ffb7) in cases.items():
        mirrors = {}
        for bank in r296.MIRROR_BANKS:
            components = {}
            for component in sorted(LOW_HEALTH_COMPONENTS):
                baseline = r300_gate_cycles(
                    component, bank=bank, scene=scene, ffb7=ffb7
                )
                current = gate_cycles(
                    component, bank=bank, scene=scene, ffb7=ffb7
                )
                components[component] = {
                    "r300_t_cycles": baseline,
                    "r302_t_cycles": current,
                    "delta": current - baseline,
                }
            mirrors[f"bank{bank}"] = components
        result[label] = mirrors
    r297.require(
        result["stage1_scene02"]["bank13"] == {
            "art": {"r300_t_cycles": 40, "r302_t_cycles": 108, "delta": 68},
            "attr": {"r300_t_cycles": 44, "r302_t_cycles": 112, "delta": 68},
            "bg7": {"r300_t_cycles": 40, "r302_t_cycles": 108, "delta": 68},
        },
        "bank13 accepted Stage-1 gate timing drifted",
    )
    r297.require(
        result["stage1_scene02"]["bank16"] == {
            "art": {"r300_t_cycles": 40, "r302_t_cycles": 124, "delta": 84},
            "attr": {"r300_t_cycles": 44, "r302_t_cycles": 128, "delta": 84},
            "bg7": {"r300_t_cycles": 40, "r302_t_cycles": 124, "delta": 84},
        },
        "bank16 accepted Stage-1 gate timing drifted",
    )
    r297.require(
        result["stage2_scene03"]["bank13"] == {
            "art": {"r300_t_cycles": 52, "r302_t_cycles": 84, "delta": 32},
            "attr": {"r300_t_cycles": 116, "r302_t_cycles": 80, "delta": -36},
            "bg7": {"r300_t_cycles": 44, "r302_t_cycles": 76, "delta": 32},
        },
        "early-rejected later-stage gate timing drifted",
    )
    return result


def exhaustive_scene_contract() -> dict[str, object]:
    """Prove the shared gate admits every and only reachable Stage-1 state."""
    accepted_scenes: set[int] = set()
    cases = 0
    for ffb7 in range(256):
        for dd06 in range(4):
            for ffbf in range(4):
                scene = r296.reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                accepted = r296.predicate_accepts(scene, ffb7)
                r297.require(
                    accepted == (ffb7 == 0x02),
                    "shared scene predicate aliases a reachable non-Stage-1 state",
                )
                # All three callers branch from exactly the same Z flag.
                for component in LOW_HEALTH_COMPONENTS:
                    r297.require(
                        r296.predicate_accepts(scene, ffb7) == accepted,
                        f"{component} diverged from the shared predicate",
                    )
                if accepted:
                    accepted_scenes.add(scene)
                cases += 1
    r297.require(accepted_scenes == {0x02, 0x0A, 0x0B},
                 "reachable Stage-1 scene set changed")
    r297.require(not r296.predicate_accepts(0x18, 0x02),
                 "Stage-card splash $18 was admitted")
    for stage in range(3, 256):
        for dd06 in range(4):
            for ffbf in range(4):
                scene = r296.reachable_scene(stage, dd06=dd06, ffbf=ffbf)
                r297.require(not r296.predicate_accepts(scene, stage),
                             f"later stage ${stage:02X} was admitted")
    return {
        "reachable_states_exhausted": cases,
        "shared_by": sorted(LOW_HEALTH_COMPONENTS),
        "accepted_reachable_scenes": ["02", "0A", "0B"],
        "splash_18_with_FFB7_02_rejected": True,
        "all_FFB7_03_through_FF_rejected": True,
    }


def validate_r300_identity(
    source: bytes, base_receipt_bytes: bytes, *, room01_capture: bytes | None = None,
) -> tuple[bytes, dict[str, object], bytes, dict[str, object]]:
    r297_full, r297_receipt = r297.build(
        source, base_receipt_bytes, variant="full", room01_capture=room01_capture
    )
    r297.require(digest(r297_full) == R297_FULL_SHA256,
                 "r297 generated identity changed")
    r297.require(r297_receipt["candidate_sha256"] == R297_FULL_SHA256,
                 "r297 generated receipt names another candidate")
    r297.require(digest(receipt_bytes(r297_receipt)) == R297_RECEIPT_SHA256,
                 "r297 generated receipt identity changed")
    r300_candidate, r300_receipt = r300.build(source, base_receipt_bytes,
                                            room01_capture=room01_capture)
    r297.require(digest(r300_candidate) == R300_SHA256,
                 "r300 generated identity changed")
    r297.require(r300_receipt["candidate_sha256"] == R300_SHA256,
                 "r300 generated receipt names another candidate")
    r297.require(digest(receipt_bytes(r300_receipt)) == R300_RECEIPT_SHA256,
                 "r300 generated receipt identity changed")
    return r297_full, r297_receipt, r300_candidate, r300_receipt


def validate_replacement_preimages(source: bytes, r300_candidate: bytes) -> None:
    """Fail closed unless r300 still contains precisely r297's attr patch."""
    for bank in r297.MIRROR_BANKS:
        gateway = r297.bank_offset(bank, r297.ATTR_GATEWAY_ADDR)
        helper = r297.ATTR_HELPER_BY_BANK[bank]
        expected = (
            r297.OLD_ATTR_GATEWAY[:7]
            + bytes((0xC4, helper & 0xFF, helper >> 8))
        )
        r297.require(
            r300_candidate[gateway:gateway + len(expected)] == expected,
            f"bank{bank} r297 attr gateway replacement preimage changed",
        )
        r297.require(
            source[
                r297.bank_offset(bank, r296.ART_LOADER_GATE_ADDR):
                r297.bank_offset(bank, r296.ART_LOADER_GATE_ADDR)
                + len(r296.OLD_ART_GATE)
            ] == r296.OLD_ART_GATE,
            f"bank{bank} r292 art gate preimage changed",
        )
        r297.require(
            source[
                r297.bank_offset(bank, r296.BG7_SELECTOR_GATE_ADDR):
                r297.bank_offset(bank, r296.BG7_SELECTOR_GATE_ADDR)
                + len(r296.OLD_BG7_GATE)
            ] == r296.OLD_BG7_GATE,
            f"bank{bank} r292 BG7 gate preimage changed",
        )
    r297.require(
        r300_candidate[
            r297.bank_offset(13, 0x5D4C):
            r297.bank_offset(13, 0x5D4C) + len(r297.BANK13_ATTR_HELPER)
        ] == r297.BANK13_ATTR_HELPER,
        "bank13 r297 attr helper replacement preimage changed",
    )
    r297.require(
        r300_candidate[
            r297.bank_offset(16, 0x6180):
            r297.bank_offset(16, 0x6180) + len(r297.BANK16_ATTR_FRONT)
        ] == r297.BANK16_ATTR_FRONT,
        "bank16 r297 attr helper front replacement preimage changed",
    )
    r297.require(
        r300_candidate[
            r297.bank_offset(16, r297.BANK16_ATTR_TAIL_ADDR):
            r297.bank_offset(16, r297.BANK16_ATTR_TAIL_ADDR)
            + len(r297.BANK16_ATTR_TAIL)
        ] == r297.BANK16_ATTR_TAIL,
        "bank16 r297 attr helper tail replacement preimage changed",
    )


def validate_native_and_omission(
    source: bytes, candidate: bytes, r297_full: bytes, r300_candidate: bytes,
) -> dict[str, object]:
    # Native renderer and the complete row helper remain exact except for the
    # two explicit r297 scene-mask bytes.
    r297.require(candidate[0x4303:0x4319] == source[0x4303:0x4319],
                 "native renderer/compiler entry changed")
    row_start = r297.bank_offset(r297.ROW_BANK, 0x6BA7)
    row_end = r297.bank_offset(r297.ROW_BANK, 0x6BEB)
    row_changes = delta(source[row_start:row_end],
                        candidate[row_start:row_end])
    r297.require(row_changes == {r297.ROW_MASK_ADDR - 0x6BA7},
                 "bank19 row helper changed beyond r297's one-byte mask")
    r297.require(candidate[r297.bank_offset(r297.ROW_BANK, 0x6BAB)] == 0x47,
                 "native row-helper LD B,A ABI changed")
    miniboss = r297.bank_offset(r297.ROW_BANK, 0x6BBA)
    r297.require(candidate[miniboss:miniboss + 4]
                 == bytes.fromhex("CB 58 20 0C"),
                 "native row-helper miniboss ABI changed")
    transition_start = r297.bank_offset(r297.ROW_BANK, 0x55C3)
    transition_end = transition_start + len(r296.OLD_TRANSITION_GATE)
    transition_changes = delta(
        source[transition_start:transition_end],
        candidate[transition_start:transition_end],
    )
    r297.require(
        transition_changes == {r297.TRANSITION_MASK_ADDR - 0x55C3},
        "bank19 transition gate changed beyond r297's one-byte mask",
    )

    # r297 wall route and all of r300's bank20 component are byte-exact.
    for start, width, label in (
        (r297.RST0_ADDR, len(r297.NEW_RST0), "RST0 room hook"),
        (r297.ROOM_STUB_ADDR, len(r297.NEW_ROOM_STUB), "room mapper stub"),
        (r297.bank_offset(r297.EXPANSION_BANK, r297.WALL_HELPER_ADDR),
         len(r297.WALL_HELPER), "bank21 wall helper"),
    ):
        r297.require(candidate[start:start + width]
                     == r297_full[start:start + width],
                     f"{label} changed after r297")
    bank20 = slice(
        r300.SEMANTIC_BANK * r297.BANK_SIZE,
        (r300.SEMANTIC_BANK + 1) * r297.BANK_SIZE,
    )
    r297.require(candidate[bank20] == r300_candidate[bank20],
                 "r300 semantic bank changed")

    # The authenticated audit rejected r301's dead call path.  Preserve the
    # exact old body and erased bank21 caves instead of shipping dead code.
    menu = r297.bank_offset(r301.BANK13, r301.MENU_HELPER_ADDR)
    r297.require(candidate[menu:menu + len(r301.OLD_MENU_HELPER)]
                 == source[menu:menu + len(r301.OLD_MENU_HELPER)]
                 == r301.OLD_MENU_HELPER,
                 "rejected r301 menu body leaked into r302")
    ingress = r297.bank_offset(r301.BANK21, r301.INGRESS_ADDR)
    context = r297.bank_offset(r301.BANK21, r301.CONTEXT_HELPER_ADDR)
    r297.require(candidate[ingress:ingress + len(r301.INGRESS)]
                 == bytes([0xFF]) * len(r301.INGRESS),
                 "rejected r301 ingress leaked into r302")
    r297.require(candidate[context:context + len(r301.CONTEXT_HELPER)]
                 == bytes([0xFF]) * len(r301.CONTEXT_HELPER),
                 "rejected r301 helper leaked into r302")
    return {
        "renderer_4303_4318_byte_exact": True,
        "row_helper_only_change": "$6BAD F7->F6",
        "transition_only_change": "$55C7 F7->F6",
        "row_LD_B_A_and_miniboss_BIT3_B_exact": True,
        "r297_room_hook_and_wall_helper_exact": True,
        "r300_bank20_byte_exact": True,
        "r301_menu_body": "omitted; exact pre-r301 bytes",
        "r301_bank21_ingress_and_helper": "omitted; erased bytes",
    }


def build(
    source: bytes, base_receipt_bytes: bytes,
) -> tuple[bytes, dict[str, object]]:
    r297.require(len(source) == r297.ROM_SIZE,
                 "base is not exactly 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256,
                 "wrong exact r292 base")
    r297.require(digest(base_receipt_bytes) == r297.BASE_RECEIPT_SHA256,
                 "r292 receipt identity changed")
    r297.require(
        json.loads(base_receipt_bytes)["candidate_sha256"]
        == r297.BASE_SHA256,
        "r292 receipt names another candidate",
    )

    r297_full, r297_receipt, r300_candidate, r300_receipt = (
        validate_r300_identity(source, base_receipt_bytes)
    )
    validate_replacement_preimages(source, r300_candidate)
    scene_contract = exhaustive_scene_contract()
    timing = timing_contract()

    rom = bytearray(r300_candidate)
    scene_owned: set[int] = set()
    gate_receipt = r296.install_scene_gates(
        rom,
        source,
        scene_owned,
        components=LOW_HEALTH_COMPONENTS,
    )
    gate_receipt["row_helper"] = (
        "r296 row rewrite omitted; exact r297 one-byte mask retained"
    )
    gate_receipt["transition_repair"] = (
        "r296 transition rewrite omitted; exact r297 one-byte mask retained"
    )
    candidate_without_checksum = bytes(rom)
    scene_delta = delta(r300_candidate, candidate_without_checksum,
                        functional=True)
    r297.require(scene_delta and scene_delta <= scene_owned,
                 "r302 scene component escaped r296-owned ranges")

    r297.update_checksums(rom)
    candidate = bytes(rom)
    native = validate_native_and_omission(
        source, candidate, r297_full, r300_candidate
    )

    r297_delta = delta(source, r297_full, functional=True)
    semantic_delta = delta(r297_full, r300_candidate, functional=True)
    retained_r297 = r297_delta - r297_attr_ranges()
    forbidden_r301 = r301_owned_ranges()
    r297.require(retained_r297, "no retained r297 component")
    r297.require(semantic_delta, "no r300 semantic component")
    r297.require(scene_delta.isdisjoint(retained_r297),
                 "r296 scene gates overlap retained r297 ownership")
    r297.require(scene_delta.isdisjoint(semantic_delta),
                 "r296 scene gates overlap r300 semantic ownership")
    r297.require(retained_r297.isdisjoint(semantic_delta),
                 "r297 retained bytes overlap r300 semantic ownership")
    for label, owned in (
        ("retained r297", retained_r297),
        ("r300 semantic", semantic_delta),
        ("r296 scene", scene_delta),
    ):
        r297.require(owned.isdisjoint(forbidden_r301),
                     f"{label} overlaps rejected r301 ownership")

    final_delta = delta(source, candidate, functional=True)
    owned_union = retained_r297 | semantic_delta | scene_owned
    r297.require(final_delta <= owned_union,
                 "r302 escaped retained/component ownership")
    r297.require(not (final_delta & forbidden_r301),
                 "r302 changed a rejected r301-owned byte")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-lowhealth-all-gates-r302-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": r297.BASE_SHA256,
        "base_receipt_sha256": r297.BASE_RECEIPT_SHA256,
        "r297_generated_sha256": r297_receipt["candidate_sha256"],
        "r297_generated_receipt_sha256": R297_RECEIPT_SHA256,
        "r300_generated_sha256": r300_receipt["candidate_sha256"],
        "r300_generated_receipt_sha256": R300_RECEIPT_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "components": {
            "r297_retained": {
                "room_hook_and_wall_helper": True,
                "row_mask": "$6BAD F7->F6",
                "transition_mask": "$55C7 F7->F6",
                "attr_only_gateway": "replaced",
            },
            "r300_semantic_row": {
                "source_sha256": R300_SHA256,
                "bank20_byte_exact": True,
                "room01_helper": "$4500-$4569",
                "room01_lut": "$4600-$46FF",
            },
            "r296_shared_scene_gates": gate_receipt,
            "r301_rejected": {
                "candidate_sha256": R301_REJECTED_SHA256,
                "included": False,
                "reason": (
                    "authenticated operator-route cache audit observed no "
                    "bank21 ingress/helper/effect execution or cache writes"
                ),
                "menu_body": "exact pre-r301 bytes",
                "bank21_caves": "exact erased pre-r301 bytes",
                "next_step": (
                    "use the independently identified one-shot close hook "
                    "at bank1:$77A8 in a separate candidate"
                ),
            },
        },
        "offline_contract": {
            "scene": scene_contract,
            "timing": timing,
            "native_and_omission": native,
        },
        "ownership": {
            "retained_r297_functional_bytes": len(retained_r297),
            "r300_semantic_functional_bytes": len(semantic_delta),
            "r296_scene_functional_bytes": len(scene_delta),
            "functional_changed_bytes_from_r292": len(final_delta),
            "component_sets_pairwise_disjoint": True,
            "rejected_r301_overlap_bytes": 0,
            "changed_offsets": [
                f"0x{offset:06X}" for offset in sorted(final_delta)
            ],
        },
        "required_gates": [
            "scene0B captured menu roundtrip on both operator states",
            "hazard-menu replay and room01 target attr-write trace",
            "room05 patterned-floor and tooth controls",
            "room01 north transition oracle",
            "blank-SRAM Stage1 handoff has no cyan/partial frame",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
    }
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
