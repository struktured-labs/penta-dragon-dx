#!/usr/bin/env python3
"""Install the rejected, non-promotable Stage-1 scanner experiment.

The dynamic hazard scanner is required whenever rotating-cylinder geometry
can be present. The strict horizontal speed fixture spends 263 of 264
publications in ordinary Stage-1 room $03, where the audited source corpus
contains no scanner-owned span. This installer bypasses only that exact
scene/room pair. Gargoyle scene $0A and every other room retain the complete
scanner. The transition repair at $55C0 still runs whenever either of its two
source classifiers can write; the proven zero-effect path pops the saved map
base and exits directly.

This is retained only to reproduce the r89/r90 negative result: even the
unsafe upper-bound variant did not meet the strict throughput target. It is
not imported by the release builder and must never be promoted or deployed.
Every changed byte still has an exact preimage so diagnostic reproduction
fails closed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
STAGE1_BANK = 19


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def _patch(
    rom: bytearray,
    bank: int,
    address: int,
    expected: bytes,
    replacement: bytes,
) -> None:
    if len(expected) != len(replacement):
        raise AssertionError(
            f"bank {bank}:${address:04X}: width-changing patch is forbidden"
        )
    offset = bank_offset(bank, address)
    actual = bytes(rom[offset:offset + len(expected)])
    if actual != expected:
        raise AssertionError(
            f"bank {bank}:${address:04X} preimage changed: expected "
            f"{expected.hex(' ')}, got {actual.hex(' ')}"
        )
    rom[offset:offset + len(replacement)] = replacement


def _header_checksum(rom: bytes | bytearray) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def _global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


@dataclass(frozen=True)
class InstallReport:
    input_sha256: str
    output_sha256: str
    skipped_scene: int
    skipped_room: int
    projected_speed_hits: int
    projected_speed_records: int
    scanner_entry: int
    transition_repair: int
    dispatcher_entry: int
    skip_leaf: int

    # Retain the builder's diagnostic-print interface while this default-off
    # experiment is evaluated.
    @property
    def key_a_samples(self) -> tuple[str, ...]:
        return ("scene02", "room03")

    @property
    def key_b_samples(self) -> tuple[str, ...]:
        return ()


def install(rom: bytearray) -> InstallReport:
    """Install the exact scene-$02/room-$03 empty-scanner bypass."""
    if len(rom) != 32 * BANK_SIZE:
        raise AssertionError(f"expected 512 KiB image, got {len(rom)} bytes")
    before = hashlib.sha256(rom).hexdigest()

    # Prove the gate's B-register premise. The helper loads exact D880 into B
    # and admits only scene $02/$0A before reaching the scanner hook. Nothing
    # between this prefix and $6BE3 writes B.
    helper_prefix = bytes.fromhex(
        "C1 FA 80 D8 47 E6 F7 FE 02 C2 50 6C FA FD DC B7 CA 50 6C"
    )
    prefix_off = bank_offset(STAGE1_BANK, 0x6BA7)
    if bytes(rom[prefix_off:prefix_off + len(helper_prefix)]) != helper_prefix:
        raise AssertionError("Stage-1 helper scene/B-register contract changed")

    # Preserve the normal DI/VBK0 preamble before dispatch. Both scanner and
    # seam-only paths therefore inherit the original entry conditions.
    _patch(
        rom,
        STAGE1_BANK,
        0x6BE3,
        bytes.fromhex("F3 AF E0 4F CD B7 61 C3 50 6C"),
        bytes.fromhex("F3 AF E0 4F C3 B5 6D 00 00 00"),
    )

    # $6DB5-$6DC8 is the explicit 20-byte row0-repair-tail allocation. BIT 3
    # distinguishes the already-admitted exact scenes ($02 ordinary, $0A
    # Gargoyle). Ordinary room $03 enters the bounded repair decision;
    # everything else calls the complete scanner.
    _patch(
        rom,
        STAGE1_BANK,
        0x6DB5,
        bytes(20),
        bytes.fromhex(
            "CB 58 20 07 F0 BD FE 03 CA 9E 6D "
            "CD B7 61 C3 50 6C 00 00 00"
        ),
    )

    # Two explicit mapper-return caves classify the only source cells that
    # $55C0 can publish after an empty scanner result. Carry means the repair
    # is still mandatory. The repair leaf itself preserves the original CALL
    # frame above the saved destination HL.
    _patch(
        rom,
        STAGE1_BANK,
        0x61A0,
        bytes(15),
        bytes.fromhex(
            "FA 21 C3 CD 88 6C C9 "
            "CD C0 55 C3 50 6C 00 00"
        ),
    )
    _patch(
        rom,
        STAGE1_BANK,
        0x6D9E,
        bytes(17),
        bytes.fromhex(
            "CD A0 61 DA A7 61 CD EF 6C DA A7 61 "
            "E1 C3 50 6C 00"
        ),
    )

    # $6CEF-$6CFB is the explicit zero gap after the live six-byte seam helper.
    # Source[$1BA]=$01 is itself repair-owned; otherwise the existing fold
    # returns Carry for the twelve real tooth IDs.
    seam_off = bank_offset(STAGE1_BANK, 0x6CE9)
    if bytes(rom[seam_off:seam_off + 6]) != bytes.fromhex(
        "1B 0E 0B C3 9B 61"
    ):
        raise AssertionError("Stage-1 seam helper preimage changed")
    _patch(
        rom,
        STAGE1_BANK,
        0x6CEF,
        bytes(13),
        bytes.fromhex("FA 5A C3 FE 01 37 C8 CD 88 6C C9") + bytes(2),
    )

    rom[0x014D] = _header_checksum(rom)
    checksum = _global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    after = hashlib.sha256(rom).hexdigest()
    return InstallReport(
        input_sha256=before,
        output_sha256=after,
        skipped_scene=0x02,
        skipped_room=0x03,
        projected_speed_hits=263,
        projected_speed_records=264,
        scanner_entry=0x61B7,
        transition_repair=0x55C0,
        dispatcher_entry=0x6DB5,
        skip_leaf=0x6CEF,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    rom = bytearray(args.input.read_bytes())
    report = install(rom)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(asdict(report), indent=2) + "\n")
    print(
        "installed Stage-1 ordinary-room scanner bypass: "
        f"{report.output_sha256}, projected "
        f"{report.projected_speed_hits}/{report.projected_speed_records}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
