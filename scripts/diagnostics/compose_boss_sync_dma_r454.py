"""Restrict r443's deferred DMA to the later-dungeon scene domain.

Bosses have FFBA != 0 too, but native arena flips need not run the dungeon
request packer. They must finish the attribute DMA synchronously. Preserve
the existing synchronous body and all its branch addresses byte-for-byte.
"""
import hashlib
import json
from pathlib import Path

from build_later_stage_deferred_dma_r443 import SYNC_PREFIX, off, update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/title-nightfall-port/d82-r453-title-attract-recovery/candidate.gb"
BASE_SHA = "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b"
OUT = ROOT / "tmp/boss-sync-dma-r454"
ENTRY = 0x6C8A  # preserve the preceding ten-byte title guard
CAVE = 0x6D20


def service():
    body = ENTRY + len(SYNC_PREFIX)
    # (scene-3) < 6 admits only dungeon scenes $03..$08. Carry-clear covers
    # Stage 1, subscenes, all nine bosses, title, and every cinematic scene.
    return (bytes.fromhex("FA80D8 D603 FE06")
            + bytes((0xD2, body & 255, body >> 8))
            + bytes.fromhex("F040 CB7F")
            + bytes((0xCA, body & 255, body >> 8))
            + bytes.fromhex("F0C4 E6F7 E0C4 3E01 C9"))


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("not the exact r453 candidate")
    start = off(23, ENTRY)
    cave = off(23, CAVE)
    code = service()
    if source[start:start + len(SYNC_PREFIX)] != SYNC_PREFIX:
        raise ValueError("deferred-DMA prefix changed")
    if source[cave:cave + len(code)] != b"\xff" * len(code):
        raise ValueError("boss DMA cave is occupied")
    result = bytearray(source)
    result[start:start + len(SYNC_PREFIX)] = bytes((0xC3, CAVE & 255, CAVE >> 8)) + bytes(len(SYNC_PREFIX) - 3)
    result[cave:cave + len(code)] = code
    update_checksums(result)
    return bytes(result)


if __name__ == "__main__":
    source = BASE.read_bytes()
    result = build(source)
    OUT.mkdir(exist_ok=True)
    rom = OUT / "candidate.gb"
    if rom.exists() and rom.read_bytes() != result:
        raise SystemExit("immutable candidate collision")
    rom.write_bytes(result)
    receipt = {"schema": "penta-boss-sync-dma-r454-v1", "experimental": True,
               "promotable": False, "base_sha256": BASE_SHA,
               "candidate_sha256": hashlib.sha256(result).hexdigest(),
               "changed_offsets": [hex(i) for i, (a,b) in enumerate(zip(source,result)) if a != b],
               "contract": "only scenes 03..08 may defer LCD-on attribute DMA; all others use unchanged synchronous body"}
    (OUT / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
