#!/usr/bin/env python3
"""Compose r534: strengthen the private Stage 4 physical-map cache key."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_story_neutral_guard_r533 as r533  # noqa: E402


PARENT_SHA256 = (
    "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba"
)
OUT = ROOT / "tmp/stage4-cache-key-r534"
BANK = 22
DELAY_SOURCE_ADDR = 0x630D
HELPER_KEY_SOURCE_ADDR = 0x6332

# The old page-pair key samples raw offsets 81/337 ($C1F1/$C2F1). It aliases
# the partially rebuilt room-$01 source exposed by r532's corrected palette
# publication timing. The replacement retains two cache bytes but XORs four
# corpus-selected cells: B=raw[210]^raw[357], C=raw[25]^raw[187].
KEY_A = (210, 357)
KEY_B = (25, 187)
OLD_DELAY_REGION = bytes.fromhex(
    "00 00 00 00 00 00 C9 00 00 00 00 00 00 00 00 00 00 00 00"
)
OLD_HELPER_REGION = bytes.fromhex(
    "21 F1 C1 46 24 4E CD 0F DB C3 92 DA"
)

# Runtime $DB0D computes C and joins the existing shared compare at $DA92.
# The two physical-map metadata records and their compare/write protocol are
# untouched. Eight trailing zero bytes retain the exact $DB20 guard boundary.
NEW_DELAY_REGION = bytes.fromhex(
    "FA B9 C1 21 5B C2 AE 4F C3 92 DA "
    "00 00 00 00 00 00 00 00"
)
# Runtime $DB32 computes B, then JR -47 to $DB0D. The unreachable two-byte pad
# keeps the installed $DB00-$DB3D payload width unchanged.
NEW_HELPER_REGION = bytes.fromhex(
    "FA 72 C2 21 05 C3 AE 47 18 D1 00 00"
)
CHECKSUM_OFFSETS = frozenset({0x14D, 0x14E, 0x14F})


def offset(address: int) -> int:
    return r518.off(BANK, address)


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r533.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r533 parent identity changed")
    rom = bytearray(parent)

    delay_offset = offset(DELAY_SOURCE_ADDR)
    helper_offset = offset(HELPER_KEY_SOURCE_ADDR)
    if parent[delay_offset:delay_offset + len(OLD_DELAY_REGION)] \
            != OLD_DELAY_REGION:
        raise ValueError("Stage 4 delay/key cave preimage changed")
    if parent[helper_offset:helper_offset + len(OLD_HELPER_REGION)] \
            != OLD_HELPER_REGION:
        raise ValueError("Stage 4 private helper preimage changed")
    rom[delay_offset:delay_offset + len(NEW_DELAY_REGION)] = NEW_DELAY_REGION
    rom[helper_offset:helper_offset + len(NEW_HELPER_REGION)] = NEW_HELPER_REGION

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed = {
        index for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    }
    functional = changed - CHECKSUM_OFFSETS
    allowed = (
        set(range(delay_offset, delay_offset + len(NEW_DELAY_REGION)))
        | set(range(helper_offset, helper_offset + len(NEW_HELPER_REGION)))
        | set(CHECKSUM_OFFSETS)
    )
    if not changed <= allowed:
        raise AssertionError("r534 parent delta escaped owned bytes")

    # Old from $DB32: 32T samples + 24T CALL + 16T NOP + 16T RET + 16T JP.
    # New: 40T first XOR + 12T JR + 40T second XOR + 16T JP.
    old_key_to_compare_t = 104
    new_key_to_compare_t = 108
    return candidate, {
        "schema": "penta-stage4-cache-key-r534-build-v1",
        "experimental": True,
        "promotable": False,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "key": {
            "register_b_offsets": list(KEY_A),
            "register_b_addresses": ["$C272", "$C305"],
            "register_c_offsets": list(KEY_B),
            "register_c_addresses": ["$C1B9", "$C25B"],
            "room_component": "$FFBD unchanged",
        },
        "runtime": {
            "first_fragment": "$DB32-$DB3B from bank22:$6332-$633B",
            "second_fragment": "$DB0D-$DB17 from bank22:$630D-$6317",
            "join": "$DA92 shared compare/write/restore",
            "old_key_to_compare_t": old_key_to_compare_t,
            "new_key_to_compare_t": new_key_to_compare_t,
            "delta_t_per_stage4_decision": (
                new_key_to_compare_t - old_key_to_compare_t
            ),
            "native_headroom_t_per_stage4_decision": 36,
        },
        "functional_changed_offsets": [
            f"0x{value:06x}" for value in sorted(functional)
        ],
        "changed_from_parent": [
            f"0x{value:06x}" for value in sorted(changed)
        ],
        "required_gates": [
            "combined retained-corpus collision/variant/replay proof",
            "Stage 4 active-map-strict semantic soak",
            "Stage 4 strict 0.99-1.01 speed",
            "r533 inherited release subset and full release matrix",
        ],
    }


def main() -> int:
    source = r518.BASE.read_bytes()
    candidate, receipt = build(source)
    OUT.mkdir(exist_ok=True)
    for path, payload in (
        (OUT / "candidate.gb", candidate),
        (OUT / "build-receipt.json", (json.dumps(receipt, indent=2) + "\n").encode()),
    ):
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"immutable output collision: {path}")
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
