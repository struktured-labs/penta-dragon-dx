#!/usr/bin/env python3
"""Build r317: define the relocated Stage-1 semantic token before first use.

r316 moves four DX scratch bytes out of the stock ``$FFA4-$FFAB`` CHR
selector array without changing any instruction width or hot-path timing.
Three relocated owners already have an explicit definition before every live
read.  The bank-13 Ted/group runtime has one exception: ``$57C7`` reads the
semantic-token latch before its first local write.

The dispatcher at bank 13 ``$5D6A`` has exactly three trailing pad bytes.
Consume those bytes to insert ``XOR A; LDH ($FF72),A`` only on the
not-installed arm, immediately before the existing jump to the installer at
``$5940``.  The installed/hot arm still jumps directly to ``$C4FC`` and the
later-dungeon arm is instruction- and cycle-identical.  The added cost is
16 T-cycles once per runtime installation.  No emulator is invoked here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_stage1_selector_latch_relocation_r316 as r316


r305 = r316.r305
ROOT = r316.ROOT
TMP = r316.TMP
BASE = r316.BASE
BASE_RECEIPT = r316.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-selector-latch-cold-init-r317/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-selector-latch-cold-init-r317/build-receipt.json"
)

BASE_SHA256 = r316.BASE_SHA256
BASE_RECEIPT_SHA256 = r316.BASE_RECEIPT_SHA256
BASE_SCHEMA = r316.BASE_SCHEMA
RELOCATION_SHA256 = r316.EXPECTED_CANDIDATE_SHA256
EXPECTED_CANDIDATE_SHA256 = (
    "77e491aa7e34711a245f0586c2434461fc6c8d3e5fad1bca0b3b27fbcfb43da0"
)

DISPATCH_BANK = 13
DISPATCH_ADDR = 0x5D6A
DISPATCH_OFFSET = r316.bank_offset(DISPATCH_BANK, DISPATCH_ADDR)
DISPATCH_PREIMAGE = bytes.fromhex(
    "FA 80 D8 D6 03 FE 06 38 15 "
    "FA 02 C6 FE 04 CA 0A 5D "
    "FA FF C5 FE C9 28 03 "
    "C3 40 59 C3 FC C4 3E 01 C9 00 00 00"
)
DISPATCH_REPLACEMENT = bytes.fromhex(
    "FA 80 D8 D6 03 FE 06 38 18 "
    "FA 02 C6 FE 04 CA 0A 5D "
    "FA FF C5 FE C9 28 06 "
    "AF E0 72 C3 40 59 C3 FC C4 3E 01 C9"
)
DISPATCH_CHANGED_RELATIVE_OFFSETS = frozenset(
    index for index, (before, after) in enumerate(
        zip(DISPATCH_PREIMAGE, DISPATCH_REPLACEMENT, strict=True)
    ) if before != after
)

TOKEN_FIRST_READ_ADDR = 0x57C7
TOKEN_FIRST_READ = bytes.fromhex(
    "F0 72 3D 28 34 3C 28 0F 3D FE 40 30 04 E0 72 18 17"
)
LOCAL_LATCH_INIT_ADDR = 0x578C
LOCAL_LATCH_INIT = bytes.fromhex(
    "44 4D D5 F8 07 AF E0 73 3E 03 E0 74"
)
SERIAL_VECTOR_ADDR = 0x0058
SERIAL_VECTOR = bytes.fromhex("3E 06 CD 61 00 C3 C3 4C")
IE_INIT_BANK = 1
IE_INIT_ADDR = 0x4032
IE_INIT = bytes.fromhex("3E 07 E0 FF")
INSTALLER_ADDR = 0x5940
INSTALLER = bytes.fromhex(
    "C5 D5 E5 21 8C 57 11 FC C4 01 24 00 CD B3 09 "
    "21 BC 57 01 24 00 CD B3 09 "
    "3E FF EA F3 C4 EA F5 C4 C3 70 59"
)
BANK13_INSTALL_FINAL_ADDR = 0x5E74
BANK13_INSTALL_FINAL = bytes.fromhex(
    "3E C9 EA FF C5 E1 D1 C1 C3 FC C4"
)
BANK16_PRIVATE_CALL_ADDR = 0x028A
BANK16_PRIVATE_CALL = bytes.fromhex("CD E4 6F")
BANK16_TRAMPOLINE_FRONT_BANK = 1
BANK16_TRAMPOLINE_FRONT_ADDR = 0x6FE4
BANK16_TRAMPOLINE_FRONT = bytes.fromhex(
    "FA 80 D8 FE 10 C2 95 42 C3 91 7C"
)
BANK16_TRAMPOLINE_TAIL_ADDR = 0x7C91
BANK16_TRAMPOLINE_TAIL = bytes.fromhex(
    "3E 10 21 00 40 E5 C3 61 00"
)
BANK16_PRIVATE_ENTRY_ADDR = 0x4000
BANK16_PRIVATE_ENTRY = bytes.fromhex(
    "F3 01 08 00 11 E0 C3 C3 DA 5C"
)
BANK16_CACHED_DISPATCH_ADDR = 0x5CDA
BANK16_CACHED_DISPATCH = bytes.fromhex(
    "FA FF C5 FE C9 CA F5 C4 C3 40 59"
)
BANK16_CACHED_FIRST_READ_ADDR = 0x58F3
BANK16_CACHED_FIRST_READ = bytes.fromhex(
    "F0 72 B9 CA D1 C5 79 E0 72"
)
BANK16_CACHED_INSTALL_FINAL_ADDR = 0x6FFF
BANK16_CACHED_INSTALL_FINAL = bytes.fromhex(
    "EA FF C5 AF E0 72 E1 D1 C1 C3 F5 C4"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def dispatch_route(scene: int, c602: int, c5ff: int) -> dict[str, Any]:
    """Model the branch contract shared by the old and new dispatcher."""
    normalized = (scene - 3) & 0xFF
    if normalized < 6:
        return {
            "route": "later-dungeon",
            "target": 0x5D8B,
            "token_write": None,
        }
    if c602 == 4:
        return {
            "route": "special-classifier",
            "target": 0x5D0A,
            "token_write": None,
        }
    if c5ff == 0xC9:
        return {
            "route": "installed-hot",
            "target": 0xC4FC,
            "token_write": None,
        }
    return {
        "route": "not-installed",
        "target": 0x5940,
        "token_write": 0,
    }


def dispatched_token_after(
    scene: int, c602: int, c5ff: int, incoming_token: int,
) -> int:
    result = dispatch_route(scene, c602, c5ff)
    token_write = result["token_write"]
    return incoming_token if token_write is None else token_write


def dispatcher_contract() -> dict[str, Any]:
    """Exhaust useful branch inputs and prove the init is cold-arm-only."""
    counts = {
        "later-dungeon": 0,
        "special-classifier": 0,
        "installed-hot": 0,
        "not-installed": 0,
    }
    for scene in range(0x100):
        for c602 in (0x00, 0x04, 0xFF):
            for c5ff in (0x00, 0xC9, 0xFF):
                result = dispatch_route(scene, c602, c5ff)
                counts[result["route"]] += 1
                if result["route"] == "not-installed":
                    r305.r304.require(
                        result["token_write"] == 0,
                        "not-installed route lost its zero-token definition",
                    )
                else:
                    r305.r304.require(
                        result["token_write"] is None,
                        "non-install route unexpectedly resets live token",
                    )
    r305.r304.require(all(counts.values()),
                      "dispatcher control partition lost a route")
    token_controls: dict[str, Any] = {}
    for incoming in (0x53, 0x57):
        cold = dispatched_token_after(0x0B, 0x00, 0x00, incoming)
        hot = dispatched_token_after(0x0B, 0x00, 0xC9, incoming)
        r305.r304.require(cold == 0,
                          "cold reinstall preserved an invalid map token")
        r305.r304.require(hot == incoming,
                          "installed hot path destroyed a live map token")
        token_controls[f"incoming_{incoming:02X}"] = {
            "not_installed_after": cold,
            "installed_hot_after": hot,
        }
    return {
        "input_tuples": 0x100 * 3 * 3,
        "route_counts": counts,
        "not_installed_token_value": 0,
        "installed_hot_token_write": None,
        "later_dungeon_token_write": None,
        "deferred_map_token_controls": token_controls,
    }


def source_preimages(source: bytes, relocated: bytes) -> dict[str, Any]:
    r305.r304.require(
        digest(source) == BASE_SHA256,
        f"r317 base identity mismatch: {digest(source)}",
    )
    r305.r304.require(
        digest(relocated) == RELOCATION_SHA256,
        "r317 in-memory r316 relocation identity mismatch",
    )
    r305.r304.require(
        relocated[
            DISPATCH_OFFSET:DISPATCH_OFFSET + len(DISPATCH_PREIMAGE)
        ] == DISPATCH_PREIMAGE,
        "r317 dispatcher/pad preimage drift",
    )
    first_read = r316.bank_offset(DISPATCH_BANK, TOKEN_FIRST_READ_ADDR)
    r305.r304.require(
        relocated[first_read:first_read + len(TOKEN_FIRST_READ)]
        == TOKEN_FIRST_READ,
        "r317 semantic-token first-read block drift",
    )
    local_init = r316.bank_offset(DISPATCH_BANK, LOCAL_LATCH_INIT_ADDR)
    r305.r304.require(
        relocated[local_init:local_init + len(LOCAL_LATCH_INIT)]
        == LOCAL_LATCH_INIT,
        "r317 A7/A8 local initializer drift",
    )
    r305.r304.require(
        relocated[SERIAL_VECTOR_ADDR:SERIAL_VECTOR_ADDR + len(SERIAL_VECTOR)]
        == SERIAL_VECTOR,
        "r317 repurposed serial-vector contract drift",
    )
    ie_init = r316.bank_offset(IE_INIT_BANK, IE_INIT_ADDR)
    r305.r304.require(
        relocated[ie_init:ie_init + len(IE_INIT)] == IE_INIT,
        "r317 IE boot initializer drift",
    )
    installer = r316.bank_offset(DISPATCH_BANK, INSTALLER_ADDR)
    r305.r304.require(
        relocated[installer:installer + len(INSTALLER)] == INSTALLER,
        "r317 installer/cache-invalidation preimage drift",
    )
    bank13_final = r316.bank_offset(
        DISPATCH_BANK, BANK13_INSTALL_FINAL_ADDR
    )
    r305.r304.require(
        relocated[
            bank13_final:bank13_final + len(BANK13_INSTALL_FINAL)
        ] == BANK13_INSTALL_FINAL,
        "r317 bank13 installer final entry drift",
    )
    r305.r304.require(
        relocated[
            BANK16_PRIVATE_CALL_ADDR:
            BANK16_PRIVATE_CALL_ADDR + len(BANK16_PRIVATE_CALL)
        ] == BANK16_PRIVATE_CALL,
        "r317 private Ted fixed call drift",
    )
    bank16_front = r316.bank_offset(
        BANK16_TRAMPOLINE_FRONT_BANK, BANK16_TRAMPOLINE_FRONT_ADDR
    )
    bank16_tail = r316.bank_offset(
        BANK16_TRAMPOLINE_FRONT_BANK, BANK16_TRAMPOLINE_TAIL_ADDR
    )
    r305.r304.require(
        relocated[
            bank16_front:bank16_front + len(BANK16_TRAMPOLINE_FRONT)
        ] == BANK16_TRAMPOLINE_FRONT,
        "r317 private Ted trampoline front drift",
    )
    r305.r304.require(
        relocated[
            bank16_tail:bank16_tail + len(BANK16_TRAMPOLINE_TAIL)
        ] == BANK16_TRAMPOLINE_TAIL,
        "r317 private Ted trampoline tail drift",
    )
    for address, expected, label in (
        (BANK16_PRIVATE_ENTRY_ADDR, BANK16_PRIVATE_ENTRY,
         "private entry"),
        (BANK16_CACHED_DISPATCH_ADDR, BANK16_CACHED_DISPATCH,
         "cached dispatcher"),
        (BANK16_CACHED_FIRST_READ_ADDR, BANK16_CACHED_FIRST_READ,
         "cached first read"),
        (BANK16_CACHED_INSTALL_FINAL_ADDR, BANK16_CACHED_INSTALL_FINAL,
         "cached installer final"),
    ):
        offset = r316.bank_offset(16, address)
        r305.r304.require(
            relocated[offset:offset + len(expected)] == expected,
            f"r317 bank16 {label} drift",
        )
    return {
        "candidate_sha256": BASE_SHA256,
        "in_memory_relocation_sha256": RELOCATION_SHA256,
        "dispatcher_preimage": "bank13:$5D6A-$5D8D exact including 3-byte pad",
        "semantic_token_first_read": "bank13:$57C7",
        "serial_vector": "fixed:$0058-$005F exact repurposed bank bridge",
        "IE_boot_init": "bank1:$4032 writes $07 (serial bit 3 clear)",
        "installer": (
            "bank13:$5940 copies runtime and writes C4F3=C4F5=FF before use"
        ),
        "bank13_installed_source": (
            "$57BC:$57C7 copies to $C520:$C52B; installer final $5E74-$5E7E exact"
        ),
        "bank16_private_route": (
            "fixed:$028A -> bank1:$6FE4/$7C91 -> bank16:$4000 -> $5CDA"
        ),
        "bank16_cached_definition": (
            "$58E0:$58F3 copies to $C53D:$C550; $7003 writes FF72=00 "
            "before $7008 jumps to $C4F5"
        ),
    }


def validate_preimages(
    source: bytes, base_receipt_bytes: bytes, relocated: bytes,
) -> dict[str, Any]:
    r305.r304.require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
                      "r317 base receipt identity mismatch")
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                      "r317 base receipt schema mismatch")
    return {**source_preimages(source, relocated),
            "build_receipt_sha256": BASE_RECEIPT_SHA256, "schema": BASE_SCHEMA}


def validate_candidate(
    source: bytes, relocated: bytes, candidate: bytes,
) -> dict[str, Any]:
    r305.r304.require(len(candidate) == len(source),
                      "r317 changed ROM size")
    r305.r304.require(
        candidate[
            DISPATCH_OFFSET:DISPATCH_OFFSET + len(DISPATCH_REPLACEMENT)
        ] == DISPATCH_REPLACEMENT,
        "r317 dispatcher replacement drift",
    )

    overlay_functional = {
        offset for offset, (before, after) in
        enumerate(zip(relocated, candidate, strict=True))
        if before != after and offset not in r316.CHECKSUM_OFFSETS
    }
    expected_overlay = {
        DISPATCH_OFFSET + relative
        for relative in DISPATCH_CHANGED_RELATIVE_OFFSETS
    }
    r305.r304.require(
        overlay_functional == expected_overlay,
        "r317 changed bytes outside the audited dispatcher overlay",
    )

    relocation_operands = {
        r316.site_offset(site) + 1 for site in r316.OPERAND_SITES
    }
    total_functional = {
        offset for offset, (before, after) in
        enumerate(zip(source, candidate, strict=True))
        if before != after and offset not in r316.CHECKSUM_OFFSETS
    }
    expected_total = (
        relocation_operands
        | {r316.CGB_FLAG_OFFSET}
        | expected_overlay
    )
    r305.r304.require(
        total_functional == expected_total,
        "r317 escaped the relocation/header/dispatcher ownership set",
    )
    for site in r316.OPERAND_SITES:
        offset = r316.site_offset(site)
        r305.r304.require(
            candidate[offset:offset + 2]
            == bytes((site.opcode, site.new_operand)),
            f"r317 lost relocation at {site.label}",
        )
    r305.r304.require(candidate[r316.CGB_FLAG_OFFSET] == r316.CGB_ONLY_FLAG,
                      "r317 lost the CGB-only hardware contract")
    return {
        "overlay_functional_changed_bytes": len(overlay_functional),
        "total_functional_changed_bytes": len(total_functional),
        "dispatcher_changed_file_offsets": [
            f"0x{offset:06X}" for offset in sorted(expected_overlay)
        ],
        "dispatcher_region": "bank13:$5D6A-$5D8D",
        "trailing_pad_consumed_bytes": 3,
        "escaped_bytes": 0,
        "rom_size_delta_bytes": 0,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    relocated, relocation_receipt = r316.construct(source)
    preimages = source_preimages(source, relocated)
    branch_contract = dispatcher_contract()

    rom = bytearray(relocated)
    rom[
        DISPATCH_OFFSET:DISPATCH_OFFSET + len(DISPATCH_REPLACEMENT)
    ] = DISPATCH_REPLACEMENT
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, relocated, candidate)
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(
            sha == EXPECTED_CANDIDATE_SHA256,
            f"r317 candidate identity drift: {sha}",
        )

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-selector-latch-cold-init-r317-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "relocation": {
            "candidate_sha256": relocation_receipt["candidate_sha256"],
            "site_count": len(r316.OPERAND_SITES),
            "mapping": {
                "FFA5": "FF01",
                "FFA7": "FF73",
                "FFA8": "FF74",
                "FFA9": "FF72",
            },
            "native_selector_collision_control": (
                relocation_receipt["offline_collision_contract"]
            ),
            "metadata_corrections": {
                "bank21_A5_sites": "Stage-2 helpers",
                "bank22_A5_sites": "Stage-7 dual-plane path",
                "serial_static_claim": (
                    "direct/immediate-C and dynamic E2/F2 executable-owner "
                    "audits and live relocated-register/SC/IE access gates "
                    "remain required; construction makes no executed-access claim"
                ),
            },
        },
        "first_use_contract": {
            "sole_missing_definition_before_r317": (
                "bank13 source $57C7 -> installed $C52B read of FF72"
            ),
            "intended_initial_semantics": "00 means no active map anchor",
            "definition_site": (
                "bank13:$5D82 XOR A; LDH ($FF72),A on not-installed arm"
            ),
            "installed_hot_path": (
                "bank13:$5D88 JP $C4FC; preserves live token"
            ),
            "later_dungeon_path": (
                "bank13:$5D8B LD A,$01; RET; no latch access"
            ),
            "A7_A8_local_definition": (
                "bank13:$5792 writes FF73=00 and $5796 writes FF74=03"
            ),
            "discarded_deferred_token_semantics": (
                "C5FF!=C9 enters $5940, whose exact preimage invalidates "
                "both map-anchor caches C4F3/C4F5 to FF; incoming 53/57 "
                "therefore resolve to no-anchor=00 and may be cleared early"
            ),
            "installed_runtime_dominance": {
                "bank13": (
                    "$5D83 defines FF72 on the sole not-installed arm; "
                    "$5E7C is the installer-final C4FC entry; source "
                    "$57C7 executes at $C52B"
                ),
                "bank16": (
                    "private Ted enters $5CDA; both cold arms reach $5940; "
                    "$7003 defines FF72 before $7008 enters C4F5; source "
                    "$58F3 executes at $C550"
                ),
            },
            "dispatcher_exhaustive_model": branch_contract,
        },
        "ownership": ownership,
        "timing": {
            "not_installed_delta_t": 16,
            "installed_hot_delta_t": 0,
            "later_dungeon_delta_t": 0,
            "instruction_width_changes_outside_consumed_pad": 0,
            "speed_regression_expected": False,
        },
        "hardware_contract": {
            "release_mode": "Game Boy Color mode required and header-enforced",
            "FF01": (
                "SB storage; promotion requires executed-opcode proof that "
                "dynamic E2/F2 never address FF01/FF02/FF72/FF73/FF74, "
                "all direct accesses match the audited owner set, and live "
                "SC.7/IE.3 stay 0"
            ),
            "FF72_FF73_FF74": (
                "CGB byte-wide registers; the same executed-owner audit plus "
                "Pocket/core read-after-write round-trip is mandatory"
            ),
            "DMG": "intentionally rejected by header byte $0143=$C0",
        },
        "required_live_gates": [
            "fresh bank13 install byte-audits source $57BC:$57C7 -> installed $C520:$C52B and observes bank13:$5D83 FF72=00 before $C52B",
            "fresh bank16 install byte-audits source $58E0:$58F3 -> installed $C53D:$C550 and observes bank16:$7003 FF72=00 before $7008->$C4F5/$C550",
            "not-installed route maps incoming FF72=53/57 to 00",
            "installed-hot route preserves seeded FF72=53/57 exactly",
            "fresh Stage1 install exercises FF01 core/row owners",
            "fresh Stage2 install byte-audits and exercises D400 FF01 owners",
            "fresh Stage7 install byte-audits and exercises DA13/dual-plane FF01 owners",
            "fresh Ted install byte-audits and exercises C4F5/C4FC FF72/FF73/FF74 owners",
            "natural death/Continue reaches bank1:$4AFB then fixed:$0C9C",
            "FFA4-FFAB equals the scene-owned selector contract at loader entry",
            "all eight VBK0 $9000-$97FF pages match canonical Stage1 art",
            "every executed E2/F2 has C outside {01,02,72,73,74}",
            "every live CPU access to FF01/FF72/FF73/FF74 matches an audited relocated owner, installed mirror, or bank13:$5D83 init; FF02 has zero live accesses",
            "SC.bit7 and IE.bit3 remain zero while FF01 is live",
            "FF01/FF72/FF73/FF74 read-after-write round-trip exactly",
            "reported menu/room/hazard visual contract is clean",
            "release speed matrix remains at least 95% for Stage1",
            "Analogue Pocket hardware pass before promotion",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    relocated, relocation_receipt = r316.build(source, base_receipt_bytes)
    preimages = validate_preimages(source, base_receipt_bytes, relocated)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-selector-latch-cold-init-r317-build-v1",
        "status": "STATIC_PASS_R317_LIVE_GATES_REQUIRED",
        "base": preimages,
        "decision": "STATIC_ROOT_FIX_COMPLETE_LIVE_GATES_REQUIRED",
    })
    receipt["relocation"]["native_selector_collision_control"] = relocation_receipt["offline_collision_contract"]
    receipt["relocation"]["metadata_corrections"]["serial_static_claim"] = (
        "no decoded executable direct/immediate-C SC owner found; "
        "dynamic E2/F2 and live relocated-register/SC/IE access "
        "gates remain required"
    )
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
