#!/usr/bin/env python3
"""Build r316: move four DX latches out of the stock CHR selector array.

The native CHR loader owns HRAM ``$FFA4-$FFAB`` as eight page selectors.
Fixed ``$0C9C`` reads that array indirectly through ``HL`` and reloads
VBK0 ``$9000-$97FF`` one 256-byte page at a time.  r314 nevertheless uses
``$FFA5/$FFA7/$FFA8/$FFA9`` as DX publication/sanitizer scratch.  A later
native reload (including the natural death/Continue route through
bank 1 ``$4AFB``) therefore consumes DX state as ROM page selectors.

Relocate every audited DX ``LDH`` operand without changing an opcode,
instruction width, or cycle count:

* ``$FFA5 -> $FF01`` (SB; SC is never started by executable game code)
* ``$FFA7 -> $FF73``
* ``$FFA8 -> $FF74``
* ``$FFA9 -> $FF72``

``$FF72-$FF74`` are byte-wide CGB registers.  The release contract already
requires Game Boy Color mode, so this overlay changes the header from the
misleading CGB-compatible ``$80`` flag to CGB-only ``$C0``.  The emitted ROM
must still pass a real Pocket round-trip gate before promotion.  No emulator
is invoked by this builder.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import build_stage1_scene0b_publication_commit_r314 as r314


r305 = r314.r305
ROOT = r314.ROOT
TMP = r314.TMP
BASE = r314.DEFAULT_OUTPUT
BASE_RECEIPT = r314.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-selector-latch-relocation-r316/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-selector-latch-relocation-r316/build-receipt.json"
)

BASE_SHA256 = r314.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "730ddfb4acc6a71dadf7404ad0e000378fe62972ff87d3a5dd0f315357819bf1"
)
BASE_SCHEMA = "penta-stage1-scene0b-publication-commit-r314-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "1373479e5a63c1adfa958ae1e278d99d32032b1d3d08386fc3a4d7641496dc2e"
)

CHECKSUM_OFFSETS = r314.CHECKSUM_OFFSETS
CGB_FLAG_OFFSET = 0x0143
CGB_COMPATIBLE_FLAG = 0x80
CGB_ONLY_FLAG = 0xC0
STOCK_SELECTOR_START = 0xFFA4
STOCK_SELECTOR_END = 0xFFAB
NATURAL_SELECTORS = bytes(range(0x10, 0x18))

# The values are low-byte LDH operands, not full addresses.
LATCH_RELOCATIONS = {
    0xA5: 0x01,
    0xA7: 0x73,
    0xA8: 0x74,
    0xA9: 0x72,
}


@dataclass(frozen=True)
class OperandSite:
    bank: int
    address: int
    opcode: int
    old_operand: int
    owner: str

    @property
    def new_operand(self) -> int:
        return LATCH_RELOCATIONS[self.old_operand]

    @property
    def access(self) -> str:
        return "write" if self.opcode == 0xE0 else "read"

    @property
    def label(self) -> str:
        return f"bank{self.bank}:${self.address:04X}"


# Executable sites only.  Raw byte pairs in graphics/tables are intentionally
# absent and must remain byte-exact.  Each address names the E0/F0 opcode; the
# one-byte operand at address+1 is the only patched byte.
OPERAND_SITES = (
    # $FFA5: atomic destination/publication latch (19 = 8 writes, 11 reads).
    OperandSite(1, 0x42AA, 0xE0, 0xA5, "atomic-destination"),
    OperandSite(1, 0x42ED, 0xF0, 0xA5, "atomic-destination"),
    OperandSite(1, 0x4328, 0xF0, 0xA5, "atomic-destination"),
    OperandSite(13, 0x5836, 0xE0, 0xA5, "stage1-atomic-route"),
    OperandSite(13, 0x7B15, 0xE0, 0xA5, "resident-installer-mirror"),
    OperandSite(16, 0x5563, 0xE0, 0xA5, "stage2-atomic-route"),
    OperandSite(16, 0x7B15, 0xE0, 0xA5, "resident-installer-mirror"),
    OperandSite(19, 0x6C51, 0xE0, 0xA5, "stage1-row-helper"),
    OperandSite(19, 0x6CCE, 0xF0, 0xA5, "stage1-row-helper"),
    OperandSite(21, 0x4307, 0xF0, 0xA5, "stage7-publication"),
    OperandSite(21, 0x4B0A, 0xF0, 0xA5, "stage7-publication"),
    OperandSite(21, 0x580B, 0xF0, 0xA5, "stage7-publication"),
    OperandSite(22, 0x7120, 0xF0, 0xA5, "later-stage-publication"),
    OperandSite(22, 0x7171, 0xF0, 0xA5, "later-stage-publication"),
    OperandSite(22, 0x719C, 0xF0, 0xA5, "later-stage-publication"),
    OperandSite(22, 0x71A2, 0xE0, 0xA5, "later-stage-publication"),
    OperandSite(22, 0x71C6, 0xF0, 0xA5, "later-stage-publication"),
    OperandSite(22, 0x71CC, 0xE0, 0xA5, "later-stage-publication"),
    OperandSite(22, 0x720C, 0xF0, 0xA5, "later-stage-publication"),

    # $FFA7: Ted materializer/sanitizer tile-mask latch
    # (11 = 5 writes, 6 reads).
    OperandSite(13, 0x546C, 0xF0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x5792, 0xE0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x5913, 0xF0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x5917, 0xE0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x591C, 0xF0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x591F, 0xE0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x5CDA, 0xF0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(13, 0x5CF1, 0xE0, 0xA7, "ted-sanitizer-mask"),
    OperandSite(16, 0x58E6, 0xE0, 0xA7, "ted-cached-plane"),
    OperandSite(16, 0x598F, 0xF0, 0xA7, "ted-cached-plane"),
    OperandSite(16, 0x5CF0, 0xF0, 0xA7, "ted-cached-plane"),

    # $FFA8: Ted sanitizer/materializer counter (10 = 7 writes, 3 reads).
    OperandSite(13, 0x53A5, 0xE0, 0xA8, "ted-sanitizer-counter"),
    OperandSite(13, 0x5462, 0xF0, 0xA8, "ted-sanitizer-counter"),
    OperandSite(13, 0x546A, 0xE0, 0xA8, "ted-sanitizer-counter"),
    OperandSite(13, 0x5796, 0xE0, 0xA8, "ted-sanitizer-counter"),
    OperandSite(13, 0x5925, 0xF0, 0xA8, "ted-sanitizer-counter"),
    OperandSite(13, 0x5928, 0xE0, 0xA8, "ted-sanitizer-counter"),
    OperandSite(13, 0x61B8, 0xE0, 0xA8, "ted-materializer-counter"),
    OperandSite(16, 0x592F, 0xE0, 0xA8, "ted-cached-plane-counter"),
    OperandSite(16, 0x5E38, 0xF0, 0xA8, "ted-cached-plane-counter"),
    OperandSite(16, 0x5E3C, 0xE0, 0xA8, "ted-cached-plane-counter"),

    # $FFA9: Ted/arena semantic-token latch (14 = 11 writes, 3 reads).
    OperandSite(13, 0x57C7, 0xF0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x57D4, 0xE0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x58FE, 0xE0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x5E39, 0xE0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x769E, 0xE0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x76A4, 0xE0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x76C8, 0xF0, 0xA9, "ted-semantic-token"),
    OperandSite(13, 0x76D0, 0xE0, 0xA9, "ted-semantic-token"),
    OperandSite(16, 0x58F3, 0xF0, 0xA9, "ted-cached-token"),
    OperandSite(16, 0x58FA, 0xE0, 0xA9, "ted-cached-token"),
    OperandSite(16, 0x7003, 0xE0, 0xA9, "ted-cached-token"),
    OperandSite(16, 0x76FC, 0xE0, 0xA9, "ted-cached-token"),
    OperandSite(17, 0x4364, 0xE0, 0xA9, "arena-semantic-token"),
    OperandSite(20, 0x60CC, 0xE0, 0xA9, "arena-semantic-token"),
)

EXPECTED_SITE_COUNTS = {0xA5: 19, 0xA7: 11, 0xA8: 10, 0xA9: 14}
EXPECTED_ACCESS_COUNTS = {
    0xA5: {"read": 11, "write": 8},
    0xA7: {"read": 6, "write": 5},
    0xA8: {"read": 3, "write": 7},
    0xA9: {"read": 3, "write": 11},
}

STOCK_READER_ADDR = 0x0C9C
STOCK_READER = bytes.fromhex(
    "21 A4 FF 06 08 16 90 C5 2A FE 40 30 09 CD 35 0D 14 C1 05 20 F2 C9"
)
STOCK_WRITER_ADDR = 0x16CD
STOCK_WRITER = bytes.fromhex(
    "11 A4 FF 0E 08 2A FE FF 28 01 12 13 0D 20 F6 C9"
)
CONTINUE_RELOAD_ADDR = 0x4AF2
CONTINUE_RELOAD = bytes.fromhex(
    "F0 DA B7 20 11 F3 31 FF DF CD 9C 0C CD C0 1E FB "
    "CD E4 41 C3 6C 01"
)

# Exact reachable latch values used by the offline collision control.  They
# are all emitted by audited DX writers in r314 and all pass stock CP $40.
REPRESENTATIVE_DX_VALUES = {0xA5: 0x00, 0xA7: 0x00, 0xA8: 0x03, 0xA9: 0x01}
STAGE1_CHR_BANK_FILE_BASE = 7 * 0x4000
CHR_PAGE_BYTES = 0x100


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return r314.bank_offset(bank, address)


def site_offset(site: OperandSite) -> int:
    return bank_offset(site.bank, site.address)


def _require_counts() -> None:
    r305.r304.require(len(OPERAND_SITES) == 54, "r316 site total drift")
    r305.r304.require(
        len({(site.bank, site.address) for site in OPERAND_SITES})
        == len(OPERAND_SITES),
        "r316 duplicate executable site",
    )
    for old_operand, expected in EXPECTED_SITE_COUNTS.items():
        sites = [site for site in OPERAND_SITES
                 if site.old_operand == old_operand]
        r305.r304.require(
            len(sites) == expected,
            f"r316 ${old_operand:02X} site-count drift",
        )
        actual_access = {
            access: sum(site.access == access for site in sites)
            for access in ("read", "write")
        }
        r305.r304.require(
            actual_access == EXPECTED_ACCESS_COUNTS[old_operand],
            f"r316 ${old_operand:02X} read/write-count drift",
        )


def source_preimages(source: bytes) -> dict[str, Any]:
    _require_counts()
    r305.r304.require(
        digest(source) == BASE_SHA256,
        f"r316 base identity mismatch: {digest(source)}",
    )
    r305.r304.require(
        source[STOCK_READER_ADDR:STOCK_READER_ADDR + len(STOCK_READER)]
        == STOCK_READER,
        "native indirect selector reader drift",
    )
    r305.r304.require(
        source[STOCK_WRITER_ADDR:STOCK_WRITER_ADDR + len(STOCK_WRITER)]
        == STOCK_WRITER,
        "native indirect selector writer drift",
    )
    r305.r304.require(
        source[bank_offset(1, CONTINUE_RELOAD_ADDR):
               bank_offset(1, CONTINUE_RELOAD_ADDR) + len(CONTINUE_RELOAD)]
        == CONTINUE_RELOAD,
        "natural death/Continue selector reload route drift",
    )
    for site in OPERAND_SITES:
        offset = site_offset(site)
        actual = source[offset:offset + 2]
        expected = bytes((site.opcode, site.old_operand))
        r305.r304.require(
            actual == expected,
            f"r316 preimage drift at {site.label}: {actual.hex()}",
        )
    return {
        "candidate_sha256": BASE_SHA256,
        "stock_selector_reader": "fixed:$0C9C-$0CB1 exact",
        "stock_selector_writer": "fixed:$16CD-$16DC exact",
        "natural_reload_route": "bank1:$4AF2-$4B08 exact",
        "audited_executable_operands": len(OPERAND_SITES),
    }


def validate_preimages(source: bytes, base_receipt_bytes: bytes) -> dict[str, Any]:
    contract = source_preimages(source)
    r305.r304.require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
                      "r316 base receipt identity mismatch")
    receipt = json.loads(base_receipt_bytes)
    r305.r304.require(receipt.get("schema") == BASE_SCHEMA,
                      "r316 base receipt schema mismatch")
    r305.r304.require(receipt.get("candidate_sha256") == BASE_SHA256,
                      "r316 base receipt/candidate mismatch")
    return {**contract, "build_receipt_sha256": BASE_RECEIPT_SHA256, "schema": BASE_SCHEMA}


def selector_collision_model(
    rom: bytes, relocated: bool,
) -> dict[str, Any]:
    """Model the native eight-page reload after representative DX writes."""
    selectors = bytearray(NATURAL_SELECTORS)
    io_state: dict[int, int] = {}
    for old_operand, value in REPRESENTATIVE_DX_VALUES.items():
        target = LATCH_RELOCATIONS[old_operand] if relocated else old_operand
        if 0xA4 <= target <= 0xAB:
            selectors[target - 0xA4] = value
        else:
            io_state[target] = value

    pages: list[bytes] = []
    for selector in selectors:
        r305.r304.require(selector < 0x40,
                          "collision control unexpectedly skipped a page")
        source = STAGE1_CHR_BANK_FILE_BASE + selector * CHR_PAGE_BYTES
        page = rom[source:source + CHR_PAGE_BYTES]
        r305.r304.require(len(page) == CHR_PAGE_BYTES,
                          "collision control source escaped ROM")
        pages.append(page)

    canonical_pages = []
    for selector in NATURAL_SELECTORS:
        source = STAGE1_CHR_BANK_FILE_BASE + selector * CHR_PAGE_BYTES
        canonical_pages.append(rom[source:source + CHR_PAGE_BYTES])
    mismatches = [
        index for index, (actual, expected) in
        enumerate(zip(pages, canonical_pages, strict=True))
        if actual != expected
    ]
    return {
        "selector_hex": bytes(selectors).hex().upper(),
        "io_state": {f"FF{key:02X}": value for key, value in io_state.items()},
        "mismatch_page_indices": mismatches,
        "mismatch_vram_pages": [f"${0x9000 + index * 0x100:04X}"
                                for index in mismatches],
        "page_sha256": [digest(page) for page in pages],
        "canonical_page_sha256": [digest(page) for page in canonical_pages],
    }


def collision_contract(source: bytes) -> dict[str, Any]:
    r314_model = selector_collision_model(source, relocated=False)
    r316_model = selector_collision_model(source, relocated=True)
    r305.r304.require(
        r314_model["selector_hex"] == "1000120003011617",
        "r314 collision control selectors drift",
    )
    r305.r304.require(
        r314_model["mismatch_page_indices"] == [1, 3, 4, 5],
        "r314 collision control did not corrupt all four owned slots",
    )
    r305.r304.require(
        r316_model["selector_hex"] == NATURAL_SELECTORS.hex().upper(),
        "r316 relocation still mutates native selectors",
    )
    r305.r304.require(
        r316_model["mismatch_page_indices"] == [],
        "r316 native reload is not eight-page canonical",
    )
    r305.r304.require(
        set(r316_model["io_state"]) == {"FF01", "FF72", "FF73", "FF74"},
        "r316 collision control did not exercise all replacement stores",
    )
    return {"r314_negative_control": r314_model, "r316": r316_model}


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(len(candidate) == len(source),
                      "r316 changed ROM size")
    operand_offsets = {site_offset(site) + 1 for site in OPERAND_SITES}
    owned_offsets = operand_offsets | {CGB_FLAG_OFFSET}
    functional = {
        offset for offset, (before, after) in
        enumerate(zip(source, candidate, strict=True))
        if before != after and offset not in CHECKSUM_OFFSETS
    }
    r305.r304.require(
        functional == owned_offsets,
        "r316 changed bytes outside the 54 audited operands and CGB flag",
    )
    for site in OPERAND_SITES:
        offset = site_offset(site)
        r305.r304.require(
            candidate[offset:offset + 2]
            == bytes((site.opcode, site.new_operand)),
            f"r316 emitted wrong relocation at {site.label}",
        )
    r305.r304.require(
        candidate[STOCK_READER_ADDR:STOCK_READER_ADDR + len(STOCK_READER)]
        == STOCK_READER,
        "r316 changed native selector reader",
    )
    r305.r304.require(
        candidate[STOCK_WRITER_ADDR:STOCK_WRITER_ADDR + len(STOCK_WRITER)]
        == STOCK_WRITER,
        "r316 changed native selector writer",
    )
    r305.r304.require(source[CGB_FLAG_OFFSET] == CGB_COMPATIBLE_FLAG,
                      "r316 base CGB-compatible flag drift")
    r305.r304.require(candidate[CGB_FLAG_OFFSET] == CGB_ONLY_FLAG,
                      "r316 did not enforce the CGB-only hardware contract")
    return {
        "functional_changed_bytes": len(functional),
        "changed_operand_offsets": [
            f"0x{offset:06X}" for offset in sorted(operand_offsets)
        ],
        "header_flag_change": "0143:80->C0",
        "opcode_changes": 0,
        "instruction_width_delta_bytes": 0,
        "instruction_cycle_delta_t": 0,
        "escaped_bytes": 0,
        "native_reader_writer_exact": True,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    collision = collision_contract(source)
    rom = bytearray(source)
    for site in OPERAND_SITES:
        rom[site_offset(site) + 1] = site.new_operand
    rom[CGB_FLAG_OFFSET] = CGB_ONLY_FLAG
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(
            sha == EXPECTED_CANDIDATE_SHA256,
            f"r316 candidate identity drift: {sha}",
        )

    per_latch: dict[str, Any] = {}
    for old_operand, new_operand in LATCH_RELOCATIONS.items():
        sites = [site for site in OPERAND_SITES
                 if site.old_operand == old_operand]
        per_latch[f"FF{old_operand:02X}->FF{new_operand:02X}"] = {
            "sites": len(sites),
            "reads": sum(site.access == "read" for site in sites),
            "writes": sum(site.access == "write" for site in sites),
            "operands": [site.label for site in sites],
        }

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-selector-latch-relocation-r316-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "root_cause": (
            "DX reused four bytes inside native FFA4-FFAB CHR page-selector "
            "state; fixed:$0C9C reads the array indirectly and a natural "
            "death/Continue reload at bank1:$4AFB turns latch values into "
            "wrong VBK0 $9100/$9300/$9400/$9500 source pages"
        ),
        "relocations": per_latch,
        "ownership": ownership,
        "offline_collision_contract": collision,
        "hardware_contract": {
            "release_mode": "Game Boy Color mode required and header-enforced",
            "FF01": (
                "SB byte storage; executed-access qualification must prove "
                "no conflicting serial owner, and live SC.bit7 and IE.bit3 "
                "must remain 0 while latches are live"
            ),
            "FF72_FF73_FF74": (
                "CGB byte-wide registers; Pocket/core round-trip required"
            ),
            "DMG": "intentionally rejected by the CGB-only header",
            "header_0143": "80->C0; header checksum repaired",
        },
        "timing": {
            "opcode_changes": 0,
            "instruction_width_delta_bytes": 0,
            "instruction_cycle_delta_t": 0,
            "speed_regression_expected": False,
        },
        "required_live_gates": [
            "cold Stage1 exercises all relocated latch owners",
            "natural death/Continue reaches bank1:$4AFB then fixed:$0C9C",
            "FFA4-FFAB equals 10 11 12 13 14 15 16 17 at loader entry",
            "all eight VBK0 $9000-$97FF pages match canonical Stage1 art",
            "SC.bit7 and IE.bit3 remain zero while FF01 is live",
            "FF01/FF72/FF73/FF74 round-trip exactly",
            "reported menu/room/hazard visual contract is clean",
            "release speed matrix remains at least 95% for Stage1",
            "Analogue Pocket hardware pass before promotion",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-selector-latch-relocation-r316-build-v1",
        "status": "STATIC_PASS_R316_COLLISION_LIVE_GATES_REQUIRED",
        "base": preimages,
        "decision": "STATIC_ROOT_FIX_LIVE_COLLISION_GATE_REQUIRED",
    })
    receipt["hardware_contract"]["FF01"] = (
        "SB byte storage; executable-code audit found no SC access or "
        "serial transfer start; live gate must assert SC.bit7 and "
        "IE.bit3 remain 0 while latches are live"
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
