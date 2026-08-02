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
) -> None:
    chunks = png_chunks(source.read_bytes())
    indices = [index for index, (kind, _) in enumerate(chunks) if kind == b"gbAs"]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")

    raw[CPU_SP:CPU_SP + 2] = (0xDFFF).to_bytes(2, "little")
    raw[CPU_PC:CPU_PC + 2] = pc.to_bytes(2, "little")
    raw[CPU_EXECUTION_STATE] = 3  # FETCH
    raw[CPU_FLAGS:CPU_FLAGS + 4] = bytes(4)
    if rom is not None:
        raw[0x0004:0x0008] = (
            zlib.crc32(rom.read_bytes()) & 0xFFFFFFFF
        ).to_bytes(4, "little")
    memory_flags = int.from_bytes(raw[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little")
    raw[MEMORY_FLAGS:MEMORY_FLAGS + 2] = (memory_flags | 0x0008).to_bytes(2, "little")
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
        "--write",
        action="append",
        type=state_write,
        default=[],
        metavar="ADDRESS=VALUE",
    )
    args = parser.parse_args()
    if not 0 <= args.pc <= 0xFFFF:
        parser.error("--pc must fit in 16 bits")
    normalize(args.source, args.destination, args.pc, args.write, args.rom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
