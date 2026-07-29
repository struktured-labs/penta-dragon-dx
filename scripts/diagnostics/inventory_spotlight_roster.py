#!/usr/bin/env python3
"""Inventory all 38 entries in the title spotlight roster.

The stock title routine increments FFF2 modulo 0x26 and uses it to index the
monster-resource table at ROM $522A.  Each idle cycle shows only three entries,
and its demo does not reliably return to the reel under automation.  Seed FFF2
immediately before the reel, then cold-boot once per identity, so every entry
gets an independent receipt.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from pyboy import PyBoy


ROSTER_TABLE_ADDR = 0x522A
ROSTER_SIZE = 0x26
ENTITY_BASE = 0xDC85
ENTITY_STRIDE = 8
SHADOW_BASES = (0xC000, 0xC100)


def visible_oam(pyboy: PyBoy) -> list[tuple[int, int, int, int, int]]:
    entries = []
    for slot in range(40):
        base = 0xFE00 + slot * 4
        y, x, tile, attr = (
            int(pyboy.memory[base + offset]) for offset in range(4)
        )
        if 0 < y < 160 and 0 < x < 168:
            entries.append((slot, y, x, tile, attr))
    return entries


def shadow_body(pyboy: PyBoy, base: int) -> list[tuple[int, int, int, int, int]]:
    entries = []
    for slot in range(4):
        entry = base + slot * 4
        y, x, tile, attr = (
            int(pyboy.memory[entry + offset]) for offset in range(4)
        )
        if 0 < y < 160 and 0 < x < 168 and 0x08 <= tile <= 0x0F:
            entries.append((slot, y, x, tile, attr))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--frames-per-identity", type=int, default=4_500)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/penta-spotlight-roster.json"),
    )
    args = parser.parse_args()

    rom_bytes = args.rom.read_bytes()
    resource_ids = list(
        rom_bytes[ROSTER_TABLE_ADDR:ROSTER_TABLE_ADDR + ROSTER_SIZE]
    )
    if len(resource_ids) != ROSTER_SIZE:
        raise SystemExit("spotlight roster table is truncated")

    hardware_samples: dict[int, int] = Counter()
    hardware_palettes: dict[int, Counter[int]] = defaultdict(Counter)
    shadow_samples: dict[int, int] = Counter()
    shadow_palettes: dict[int, Counter[int]] = defaultdict(Counter)
    observed_resources: dict[int, Counter[int]] = defaultdict(Counter)
    resource_graphics: dict[int, bytes] = {}
    first_seen: dict[int, int] = {}
    scene_counts: dict[int, Counter[int]] = defaultdict(Counter)

    for target in range(ROSTER_SIZE):
        pyboy = PyBoy(
            str(args.rom.resolve()), window="null", cgb=True, sound=False
        )
        pyboy.set_emulation_speed(0)
        seeded = False
        try:
            for frame in range(1, args.frames_per_identity + 1):
                pyboy.tick(1, False)
                scene = int(pyboy.memory[0xD880])
                scene_counts[target][scene] += 1

                # $516F increments FFF2 before using it, so seed target-1
                # during the preceding sliding-banner scene.
                if scene == 0x1C and not seeded:
                    pyboy.memory[0xFFF2] = (target - 1) % ROSTER_SIZE
                    seeded = True
                if scene != 0x1B or int(pyboy.memory[0xFFF2]) != target:
                    continue

                first_seen.setdefault(target, frame)
                observed_resources[target].update(
                    [int(pyboy.memory[ENTITY_BASE])]
                )

                hardware = [
                    entry for entry in visible_oam(pyboy)
                    if entry[0] < 4 and 0x08 <= entry[3] <= 0x0F
                ]
                if len(hardware) == 4:
                    hardware_samples[target] += 1
                    hardware_palettes[target].update(
                        entry[4] & 7 for entry in hardware
                    )

                shadows = [
                    body
                    for base in SHADOW_BASES
                    if len(body := shadow_body(pyboy, base)) == 4
                ]
                if shadows:
                    shadow_samples[target] += 1
                    shadow_palettes[target].update(
                        entry[4] & 7 for entry in shadows[0]
                    )
                    resource_graphics.setdefault(
                        target,
                        bytes(
                            int(pyboy.memory[0x8000 + offset])
                            for offset in range(0x80)
                        ),
                    )

                # A few dozen visible samples are enough to prove whether the
                # native body reached hardware OAM and which palette it uses.
                if hardware_samples[target] >= 48:
                    break
        finally:
            pyboy.stop(save=False)

    rows = []
    for identity, resource in enumerate(resource_ids):
        rows.append(
            {
                "identity": identity,
                "resource_id": resource,
                "first_seen": first_seen.get(identity),
                "hardware_samples": hardware_samples[identity],
                "hardware_palettes": dict(
                    sorted(hardware_palettes[identity].items())
                ),
                "shadow_samples": shadow_samples[identity],
                "shadow_palettes": dict(
                    sorted(shadow_palettes[identity].items())
                ),
                "observed_resources": dict(
                    sorted(observed_resources[identity].items())
                ),
                "graphics_vram": "0x8000:0x8080",
                "graphics_sha256": (
                    hashlib.sha256(resource_graphics[identity]).hexdigest()
                    if identity in resource_graphics else None
                ),
                "graphics_hex": (
                    resource_graphics[identity].hex()
                    if identity in resource_graphics else None
                ),
            }
        )

    receipt = {
        "rom": str(args.rom.resolve()),
        "frames_per_identity": args.frames_per_identity,
        "roster_table_address": f"0x{ROSTER_TABLE_ADDR:04X}",
        "resource_ids": resource_ids,
        "identities_seen": len(first_seen),
        "identities_reaching_hardware": sum(
            samples > 0 for samples in hardware_samples.values()
        ),
        "scene_counts": {
            str(identity): dict(sorted(counts.items()))
            for identity, counts in sorted(scene_counts.items())
        },
        "roster": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    for row in rows:
        print(
            f"{row['identity']:02d} resource={row['resource_id']:02X} "
            f"first={str(row['first_seen']):>6s} "
            f"hw={row['hardware_samples']:3d}/{row['hardware_palettes']} "
            f"shadow={row['shadow_samples']:3d}/{row['shadow_palettes']}"
        )
    print(
        f"Seen {len(first_seen)}/{ROSTER_SIZE} identities; "
        f"{sum(samples > 0 for samples in hardware_samples.values())}/"
        f"{ROSTER_SIZE} reached hardware OAM. "
        f"Receipt: {args.output.resolve()}"
    )
    return 0 if len(first_seen) == ROSTER_SIZE else 1


if __name__ == "__main__":
    raise SystemExit(main())
