#!/usr/bin/env python3
"""Move an mGBA Game Boy savestate to a shared fixed-bank resume point.

This is for cross-build diagnostics only.  Old states are often serialized
inside code that a newer ROM replaces, so executing their saved PC can create
false corruption before a comparison begins.  The normalized state resumes
at the stock main loop with a clean stack and fetch state while preserving all
game, video, and input memory from the source state.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import zlib


GB_STATE_SIZE = 0x11800
CPU_SP = 0x0028
CPU_PC = 0x002A
CPU_EXECUTION_STATE = 0x0039
CPU_FLAGS = 0x0044
MEMORY_FLAGS = 0x0194
MEMORY_CURRENT_BANK = 0x0168
MBC1_BANK_LO = 0x0186
MBC1_BANK_HI = 0x0187
MAIN_LOOP_BANK = 1
# DX uses this census-free HRAM byte as a transition-owned Gargoyle prelude
# gate. Real boots initialize it on the title path. Cross-ROM fixtures bypass
# that path, so arm the gate unless a diagnostic explicitly overrides it.
ATTRACT_PRELUDE_FLAG = 0xFF91
# A cross-ROM state can retain the source build's scene identity while its
# mutable C600 palette table still belongs to an earlier scene/build. Force
# one ordinary current-ROM transition; explicit diagnostic writes below may
# intentionally override this default.
SCENE_CACHE = 0xDF0D
ARENA_GEOMETRY_SOURCE_BANK = 13
ARENA_GEOMETRY_SOURCE_ADDR = 0x563A
ARENA_GEOMETRY_RUNTIME_ADDR = 0xDB80
ARENA_GEOMETRY_SIZE = 36
RUNTIME_HELPER_BANK = 13
RUNTIME_HELPER_SOURCE_A = 0x7BB2
RUNTIME_HELPER_SOURCE_B = 0x7C4D
RUNTIME_HELPER_SPLIT = 0x7BE0 - RUNTIME_HELPER_SOURCE_A
RUNTIME_HELPER_ADDR = 0xDA60
RUNTIME_HELPER_SIZE = 0xA0


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("input is not an mGBA PNG savestate")
    chunks: list[tuple[bytes, bytes]] = []
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if len(payload) != length:
            raise RuntimeError("truncated PNG savestate chunk")
        chunks.append((kind, payload))
        offset += 12 + length
    return chunks


def write_png(path: Path, chunks: list[tuple[bytes, bytes]]) -> None:
    data = bytearray(b"\x89PNG\r\n\x1a\n")
    for kind, payload in chunks:
        data.extend(struct.pack(">I", len(payload)))
        data.extend(kind)
        data.extend(payload)
        data.extend(struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    path.write_bytes(data)


def state_offset(address: int) -> int:
    """Translate the WRAM/HRAM bus ranges used by diagnostics."""
    if 0xC000 <= address <= 0xDFFF:
        return 0x4400 + address - 0xC000
    if 0xFF80 <= address <= 0xFFFF:
        return 0x0380 + address - 0xFF80
    raise ValueError(f"unsupported state write address 0x{address:04X}")


def state_write(value: str) -> tuple[int, int]:
    try:
        raw_address, raw_value = value.split("=", 1)
        address, byte = int(raw_address, 0), int(raw_value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("writes must be ADDRESS=VALUE") from error
    if not 0 <= address <= 0xFFFF or not 0 <= byte <= 0xFF:
        raise argparse.ArgumentTypeError("write address/value is out of range")
    try:
        state_offset(address)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return address, byte


def normalize(
    source: Path,
    destination: Path,
    pc: int,
    writes: list[tuple[int, int]],
    rom: Path | None = None,
    bank: int | None = None,
    retarget_only: bool = False,
    preserve_machine: bool = False,
    arena_table: int | None = None,
) -> None:
    chunks = png_chunks(source.read_bytes())
    indices = [index for index, (kind, _) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")

    if retarget_only or preserve_machine:
        if rom is None:
            raise ValueError("machine-preserving modes require a ROM")
        if writes or bank is not None:
            raise ValueError(
                "machine-preserving modes cannot use --write or --bank"
            )
        raw[0x0004:0x0008] = (
            zlib.crc32(rom.read_bytes()) & 0xFFFFFFFF
        ).to_bytes(4, "little")
        if arena_table is not None:
            rom_bytes = rom.read_bytes()
            source = (
                13 * 0x4000
                + (0x7200 + arena_table * 0x100 - 0x4000)
            )
            table = rom_bytes[source:source + 0x100]
            if len(table) != 0x100 or any(value > 7 for value in table):
                raise ValueError("candidate arena table is missing or invalid")
            table_destination = state_offset(0xC600)
            raw[table_destination:table_destination + 0x100] = table
            raw[state_offset(SCENE_CACHE)] = 0x0C + arena_table
            # Live fixtures have already passed cold-boot initialization, so
            # their DB80 helper belongs to the source ROM just like C600 did.
            # Retarget both candidate-owned runtime payloads while leaving the
            # CPU, stack, mapper, native game RAM, and video state untouched.
            geometry_source = (
                ARENA_GEOMETRY_SOURCE_BANK * 0x4000
                + ARENA_GEOMETRY_SOURCE_ADDR - 0x4000
            )
            geometry = rom_bytes[
                geometry_source:geometry_source + ARENA_GEOMETRY_SIZE
            ]
            if len(geometry) != ARENA_GEOMETRY_SIZE:
                raise ValueError("candidate arena geometry helper is missing")
            geometry_destination = state_offset(ARENA_GEOMETRY_RUNTIME_ADDR)
            raw[
                geometry_destination:
                geometry_destination + len(geometry)
            ] = geometry
            # The always-mapped DA60-DAFF decision helper is likewise ROM-
            # owned. Its source is split around the live free-slot emitter;
            # concatenate the two exact bank-13 fragments so states remain
            # valid when a candidate changes the helper's internal ABI.
            helper_a_source = (
                RUNTIME_HELPER_BANK * 0x4000
                + RUNTIME_HELPER_SOURCE_A - 0x4000
            )
            helper_b_source = (
                RUNTIME_HELPER_BANK * 0x4000
                + RUNTIME_HELPER_SOURCE_B - 0x4000
            )
            helper = (
                rom_bytes[
                    helper_a_source:
                    helper_a_source + RUNTIME_HELPER_SPLIT
                ]
                + rom_bytes[
                    helper_b_source:
                    helper_b_source
                    + RUNTIME_HELPER_SIZE - RUNTIME_HELPER_SPLIT
                ]
            )
            if len(helper) != RUNTIME_HELPER_SIZE:
                raise ValueError("candidate DA60 helper is missing")
            helper_destination = state_offset(RUNTIME_HELPER_ADDR)
            raw[
                helper_destination:helper_destination + len(helper)
            ] = helper
        chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
        write_png(destination, chunks)
        return

    raw[CPU_SP:CPU_SP + 2] = (0xDFFF).to_bytes(2, "little")
    raw[CPU_PC:CPU_PC + 2] = pc.to_bytes(2, "little")
    raw[CPU_EXECUTION_STATE] = 3  # FETCH
    raw[CPU_FLAGS:CPU_FLAGS + 4] = bytes(4)
    if bank is not None:
        # Some fixtures were captured midway through a bank-13 helper while
        # FF99 still advertised bank 1. A fixed-bank PC alone cannot repair
        # that mismatch: the first Timer IRQ restores the wrong code page.
        # Make bank normalization explicit because other live fixtures depend
        # on retaining the captured switchable bank after their main-loop
        # landing.
        raw[MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2] = (
            bank
        ).to_bytes(2, "little")
        raw[MBC1_BANK_LO] = bank
        raw[MBC1_BANK_HI] = 0
        raw[state_offset(0xFF99)] = bank
    if rom is not None:
        raw[0x0004:0x0008] = (
            zlib.crc32(rom.read_bytes()) & 0xFFFFFFFF
        ).to_bytes(4, "little")
    memory_flags = int.from_bytes(raw[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little")
    raw[MEMORY_FLAGS:MEMORY_FLAGS + 2] = (memory_flags | 0x0008).to_bytes(2, "little")
    raw[state_offset(ATTRACT_PRELUDE_FLAG)] = 1
    raw[state_offset(SCENE_CACHE)] = 0xFF
    for address, value in writes:
        raw[state_offset(address)] = value
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(destination, chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pc", type=lambda value: int(value, 0), default=0x016C)
    parser.add_argument(
        "--rom",
        type=Path,
        help="retarget the serialized ROM CRC for a cross-build comparison",
    )
    parser.add_argument(
        "--bank",
        type=lambda value: int(value, 0),
        help="also normalize the mapped MBC1 bank and FF99 bank shadow",
    )
    parser.add_argument(
        "--retarget-only",
        action="store_true",
        help=(
            "change only the serialized ROM CRC; preserve CPU, stack, bank, "
            "fetch state, and all memory byte-for-byte"
        ),
    )
    parser.add_argument(
        "--preserve-machine",
        action="store_true",
        help=(
            "preserve CPU, stack, bank, fetch state, and runtime memory while "
            "retargeting the ROM CRC; may be combined with --arena-table"
        ),
    )
    parser.add_argument(
        "--arena-table",
        type=int,
        choices=range(9),
        help="inject the selected candidate bank-13 arena LUT into WRAM C600",
    )
    parser.add_argument(
        "--write",
        action="append",
        type=state_write,
        default=[],
        metavar="ADDRESS=VALUE",
    )
    args = parser.parse_args()
    if not 0 <= args.pc <= 0xFFFF:
        parser.error("--pc must fit in 16 bits")
    if args.bank is not None and not 1 <= args.bank <= 0x1F:
        parser.error("--bank must be in the mapped MBC1 range 1..31")
    if args.retarget_only and args.rom is None:
        parser.error("--retarget-only requires --rom")
    if args.preserve_machine and args.rom is None:
        parser.error("--preserve-machine requires --rom")
    if args.retarget_only and args.preserve_machine:
        parser.error("choose only one machine-preserving mode")
    if args.arena_table is not None and not args.preserve_machine:
        parser.error("--arena-table requires --preserve-machine")
    normalize(
        args.source, args.destination, args.pc, args.write, args.rom,
        bank=args.bank,
        retarget_only=args.retarget_only,
        preserve_machine=args.preserve_machine,
        arena_table=args.arena_table,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
