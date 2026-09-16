"""Move Riff/Crystal/Troop LUT data away from live bank13 code overlays."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_v302_title_fix import _bg_table_riff, _bg_table_crystal_dragon, _bg_table_troop
from build_later_hdma_overlap import Asm
from compose_boss_sync_dma_r454 import off, update_checksums

BASE = ROOT / "tmp/boss-sync-dma-r454/candidate.gb"
BASE_SHA = "9e1bbb5165e8f9e772dbaef2eb7b2cd05260deeb7b1cf230e2f3f98904f8881e"
OUT = ROOT / "tmp/arena-palette-storage-r455"
TITLE_GUARD = bytes.fromhex("FA80D8 FE01 2003 3E01 C9")
TABLE_BUILDERS = {0x73: _bg_table_riff, 0x74: _bg_table_crystal_dragon, 0x77: _bg_table_troop}


def dispatch():
    a = Asm(0x6E00)
    a.db(0x7C, 0xFE, 0x72)
    a.jr(0x38, "dma")
    a.db(0xFE, 0x7B)
    a.jp(0xDA, "table")
    a.label("dma")
    a.db(*TITLE_GUARD, 0xC3, 0x8A, 0x6C)
    a.label("table")
    a.db(0xC3, 0x40, 0x6E)
    return a.finish()


def loader():
    a = Asm(0x6E40)
    a.db(0x3E, 0x5A, 0xEA, 0x02, 0xDF, 0x7C)
    for page in TABLE_BUILDERS:
        a.db(0xFE, page)
        a.jr(0x28, "copy")
    a.db(0x3E, 0x0D, 0xC9)
    a.label("copy")
    a.db(0x11, 0x00, 0xC6, 0x06, 0x00)
    a.label("byte")
    a.db(0x2A, 0x12, 0x13, 0x05)
    a.jr(0x20, "byte")
    # The existing bank13 copy loop remains intact. For repaired tables it
    # copies the new C600 table onto itself; all other arena sources stay HL.
    a.db(0x21, 0x00, 0xC6, 0x3E, 0x0D, 0xC9)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("not exact r454")
    bank13 = source[13 * 0x4000:14 * 0x4000]
    signature = bytes.fromhex("C672673E5AEA02DF2E0018")
    if bank13.count(signature) != 1:
        raise ValueError("arena table selector is not unique")
    site = 13 * 0x4000 + bank13.index(signature) + 3
    if source[off(23, 0x6C80):off(23, 0x6C8A)] != TITLE_GUARD:
        raise ValueError("title guard changed")
    result = bytearray(source)
    def put_free(address, data):
        start = off(23, address)
        if source[start:start + len(data)] != b"\xff" * len(data):
            raise ValueError(f"bank23 cave occupied at {address:04X}")
        result[start:start + len(data)] = data
    put_free(0x6E00, dispatch())
    put_free(0x6E40, loader())
    for page, fn in TABLE_BUILDERS.items():
        data = bytes(fn())
        assert len(data) == 256 and max(data) <= 7 and data[-1] == 0
        put_free(page << 8, data)
    result[off(23, 0x6C80):off(23, 0x6C8A)] = bytes.fromhex("C3006E") + bytes(7)
    # Keep the original JR opcode/displacement at +7/+8 unchanged.
    result[site:site + 7] = bytes.fromhex("2E00 3E17 CD4708")
    update_checksums(result)
    return bytes(result), site


if __name__ == "__main__":
    source = BASE.read_bytes()
    result, site = build(source)
    OUT.mkdir(exist_ok=True)
    rom = OUT / "candidate.gb"
    if rom.exists() and rom.read_bytes() != result:
        raise SystemExit("immutable candidate collision")
    rom.write_bytes(result)
    receipt = {"schema": "penta-arena-palette-storage-r455-v1", "experimental": True,
               "promotable": False, "base_sha256": BASE_SHA,
               "candidate_sha256": hashlib.sha256(result).hexdigest(),
               "selector_site": hex(site),
               "tables": {hex(p): hashlib.sha256(bytes(fn())).hexdigest() for p, fn in TABLE_BUILDERS.items()},
               "changed_offsets": [hex(i) for i,(a,b) in enumerate(zip(source,result)) if a != b]}
    (OUT / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(receipt["candidate_sha256"], "selector", hex(site))
