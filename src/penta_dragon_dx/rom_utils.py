import zlib
from pathlib import Path
from typing import Iterable

# Common ROM sizes for quick sanity; not authoritative
EXPECTED_SIZES = {0x8000, 0x10000, 0x20000, 0x40000, 0x80000, 0x100000, 0x200000, 0x400000}

CARTRIDGE_TYPES = {
    0x00: "ROM ONLY",
    0x01: "MBC1",
    0x02: "MBC1+RAM",
    0x03: "MBC1+RAM+BATTERY",
    0x05: "MBC2",
    0x06: "MBC2+BATTERY",
    0x08: "ROM+RAM",
    0x09: "ROM+RAM+BATTERY",
    0x0F: "MBC3+TIMER+BATTERY",
    0x10: "MBC3+TIMER+RAM+BATTERY",
    0x11: "MBC3",
    0x12: "MBC3+RAM",
    0x13: "MBC3+RAM+BATTERY",
    0x19: "MBC5",
    0x1A: "MBC5+RAM",
    0x1B: "MBC5+RAM+BATTERY",
    0x1C: "MBC5+RUMBLE",
    0x1D: "MBC5+RUMBLE+RAM",
    0x1E: "MBC5+RUMBLE+RAM+BATTERY",
    0x20: "MBC6",
    0x22: "MBC7+SENSOR+RUMBLE+RAM+BATTERY",
}

ROM_SIZE_TABLE = {
    0x00: 32 * 1024,
    0x01: 64 * 1024,
    0x02: 128 * 1024,
    0x03: 256 * 1024,
    0x04: 512 * 1024,
    0x05: 1 * 1024 * 1024,
    0x06: 2 * 1024 * 1024,
    0x07: 4 * 1024 * 1024,
    0x08: 8 * 1024 * 1024,
    0x52: int(1.1 * 1024 * 1024),
    0x53: int(1.2 * 1024 * 1024),
    0x54: int(1.5 * 1024 * 1024),
}

RAM_SIZE_TABLE = {
    0x00: 0,
    0x01: 2 * 1024,
    0x02: 8 * 1024,
    0x03: 32 * 1024,  # 4 banks
    0x04: 128 * 1024,  # 16 banks
    0x05: 64 * 1024,  # 8 banks
}


def read_rom_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def write_rom_bytes(path: str | Path, data: bytes) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _header_checksum(data: bytes) -> int:
    x = 0
    for i in range(0x0134, 0x014D):
        x = (x - data[i] - 1) & 0xFF
    return x


def _global_checksum(data: bytes) -> int:
    # 16-bit sum over all bytes; typically stored at 0x14E-0x14F (and included in the sum)
    return sum(data) & 0xFFFF


def parse_header(data: bytes) -> dict:
    if len(data) < 0x150:
        raise ValueError("ROM too small to contain a valid header")
    title_raw = data[0x0134:0x0144]
    # Strip trailing nulls and non-printables
    title = bytes(b for b in title_raw if 32 <= b <= 126).decode("ascii", errors="ignore").strip()
    cgb_flag = data[0x0143]
    sgb_flag = data[0x0146]
    cart_type = data[0x0147]
    rom_size_code = data[0x0148]
    ram_size_code = data[0x0149]
    dest_code = data[0x014A]
    old_lic = data[0x014B]
    version = data[0x014C]
    hdr_chk = data[0x014D]
    glb_chk = int.from_bytes(data[0x014E:0x0150], "big")

    header = {
        "title": title or "(unknown)",
        "cgb_flag": cgb_flag,
        "cgb_support": "CGB-only" if (cgb_flag & 0xC0) == 0xC0 else ("CGB-supported" if (cgb_flag & 0x80) else "DMG-only/unspecified"),
        "sgb_flag": sgb_flag,
        "cartridge_type": cart_type,
        "cartridge_type_name": CARTRIDGE_TYPES.get(cart_type, f"Unknown(0x{cart_type:02X})"),
        "rom_size_code": rom_size_code,
        "rom_size_expected": ROM_SIZE_TABLE.get(rom_size_code),
        "ram_size_code": ram_size_code,
        "ram_size_expected": RAM_SIZE_TABLE.get(ram_size_code),
        "destination_code": dest_code,
        "old_licensee": old_lic,
        "version": version,
        "header_checksum": hdr_chk,
        "header_checksum_calc": _header_checksum(data),
        "global_checksum": glb_chk,
        "global_checksum_calc": _global_checksum(data),
    }
    return header


def inspect_rom(path: str | Path) -> dict:
    data = read_rom_bytes(path)
    size = len(data)
    c = crc32(data)
    info = {"size": size, "crc32": c}
    if size not in EXPECTED_SIZES:
        info["warning"] = "Unexpected ROM size. Confirm banking layout."
    try:
        header = parse_header(data)
        info["header"] = header
        if header["header_checksum"] != header["header_checksum_calc"]:
            info["header_warning"] = "Header checksum mismatch"
    except Exception as e:
        info["header_error"] = str(e)
    return info


def find_palette_hook_candidates(data: bytes, window: int = 32) -> list[int]:
    # Very naive heuristic: search for sequences that write to CGB palette registers (0xFF69/0xFF6B etc.)
    # In raw ROM this is pre-init; actual writes occur at runtime in RAM, so this is placeholder logic.
    # We look for instruction bytes: LDH (0xE0) followed by immediate like 0x69 or 0x6B.
    matches = []
    for i in range(len(data) - 1):
        if data[i] == 0xE0 and data[i + 1] in (0x69, 0x6B):
            matches.append(i)
    return matches


def find_free_space(data: bytes, min_len: int = 64, pad_bytes: Iterable[int] = (0xFF, 0x00)):
    regions = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b in pad_bytes:
            start = i
            pad = b
            while i < n and data[i] == pad:
                i += 1
            length = i - start
            if length >= min_len:
                regions.append({
                    "offset": start,
                    "length": length,
                    "pad": pad,
                    "bank": start // 0x4000,
                    "bank_addr": 0x4000 + (start % 0x4000) if start >= 0x4000 else start,
                })
        else:
            i += 1
    regions.sort(key=lambda r: r["length"], reverse=True)
    return regions
