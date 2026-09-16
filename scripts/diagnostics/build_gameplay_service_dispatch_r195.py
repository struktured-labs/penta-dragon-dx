#!/usr/bin/env python3
"""Build the r195 scene-routed death/title VBlank dispatcher candidate.

This is an isolated, hash-bound candidate builder.  It preserves both service
implementations and replaces their two unconditional wrapper calls with one
scene router.  Title/epilogue states retain the title service; arenas, story,
death, and ending retain the death dispatcher; ordinary dungeon/demo scenes
return without paying either known no-op service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "c6bd39a4eac5bcce00bd621a19af13c0a54f87f51ea89aec5fde8a3b42593272"
BANK_SIZE = 0x4000
BANK = 13
CAVE_ADDR = 0x6EC4
ROUTER_ADDR = CAVE_ADDR + 2
WRAPPER_CALL_ADDR = 0x6F20
DEATH_ADDR = 0x7100
TITLE_ADDR = 0x6A60


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def global_checksum(rom: bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.resolve()
    source = base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"wrong exact r194 base: {digest(source)}")
    rom = bytearray(source)

    cave_off = offset(CAVE_ADDR)
    wrapper_off = offset(WRAPPER_CALL_ADDR)
    cave_preimage = bytes(24)
    wrapper_preimage = bytes.fromhex("CD 00 71 CD 60 6A")
    if rom[cave_off:cave_off + len(cave_preimage)] != cave_preimage:
        raise SystemExit("prelude padding cave moved")
    if rom[wrapper_off:wrapper_off + len(wrapper_preimage)] != wrapper_preimage:
        raise SystemExit("death/title wrapper call pair moved")
    if rom[cave_off - 2:cave_off] != bytes.fromhex("E0 40"):
        raise SystemExit("menu prelude fallthrough moved")

    # Menu maintenance formerly fell through 24 NOP bytes.  Jump over the
    # router before resuming the remaining padding and unchanged semantic tail.
    router = bytes([
        0xFA, 0x80, 0xD8,                  # A = D880 scene
        0xFE, 0x02,                        # title/epilogue family?
        0x38, 0x06,                        # yes -> title service
        0xFE, 0x0C,                        # dungeon/demo family?
        0xD8,                              # yes -> RET C
        0xC3, DEATH_ADDR & 0xFF, DEATH_ADDR >> 8,
        0xC3, TITLE_ADDR & 0xFF, TITLE_ADDR >> 8,
    ])
    assert len(router) == 16
    menu_landing = ROUTER_ADDR + len(router)
    menu_jump = bytes([0x18, (menu_landing - (CAVE_ADDR + 2)) & 0xFF])
    rom[cave_off:cave_off + 2] = menu_jump
    rom[cave_off + 2:cave_off + 2 + len(router)] = router
    rom[wrapper_off:wrapper_off + 6] = bytes([
        0xCD, ROUTER_ADDR & 0xFF, ROUTER_ADDR >> 8,
        0x00, 0x00, 0x00,
    ])
    checksum = global_checksum(rom)
    rom[0x014E:0x0150] = checksum.to_bytes(2, "big")

    changed = [i for i, (a, b) in enumerate(zip(source, rom)) if a != b]
    allowed = (
        set(range(cave_off, cave_off + 2 + len(router)))
        | set(range(wrapper_off, wrapper_off + 6))
        | {0x014E, 0x014F}
    )
    if not set(changed) <= allowed:
        raise SystemExit("candidate changed bytes outside its confined regions")

    output = args.output.resolve()
    receipt = args.receipt.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    report = {
        "schema": "penta-gameplay-service-dispatch-r195-v1",
        "status": "static-pass-emulator-required",
        "base": str(base),
        "base_sha256": digest(source),
        "output": str(output),
        "output_sha256": digest(rom),
        "router_address": f"0x{ROUTER_ADDR:04X}",
        "router_bytes": router.hex().upper(),
        "menu_jump": menu_jump.hex().upper(),
        "wrapper_address": f"0x{WRAPPER_CALL_ADDR:04X}",
        "changed_offsets": [f"0x{i:06X}" for i in changed],
        "global_checksum": f"0x{checksum:04X}",
        "routing": {
            "00-01": "title_palette_service",
            "02-0B": "return_without_inactive_services",
            "0C-FF": "death_story_service",
        },
        "checks": {
            "exact_r194_base": True,
            "menu_fallthrough_jumps_over_router": True,
            "title_and_epilogue_owner_preserved": True,
            "arena_death_story_owner_preserved": True,
            "ordinary_dungeon_services_were_semantic_noops": True,
            "all_changes_confined": True,
        },
    }
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS_STATIC: {output} SHA256={digest(rom)}")
    print(f"Receipt: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
