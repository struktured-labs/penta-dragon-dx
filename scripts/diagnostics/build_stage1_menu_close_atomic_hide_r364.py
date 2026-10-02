#!/usr/bin/env python3
"""Build r364: close the native menu with an atomic Window hide.

r363's Scene-$0B menu wrapper hides the hardware Window and then executes
``EI`` before the native exit clears ``FFE4``.  A VBlank accepted after that
``EI`` can still observe menu ownership and republish the Window on Pocket.
Keep interrupts disabled through the ownership clear, hide the Window again,
and only then restore IME and return to bank 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-fast-final-window-selector-r363/candidate.gb"
BASE_RECEIPT = TMP / "stage1-fast-final-window-selector-r363/build-receipt.json"
BASE_SHA256 = "9a85f55b87f3450cd279556a17ed6bb6865298dc73b327fdbba70fdf0bc4a030"
BASE_RECEIPT_SHA256 = (
    "4078b328bfc9723759c3183b6b592fb9c57c76480931b5d3f8d9678dab3d2f09"
)
DEFAULT_OUTPUT = TMP / "stage1-menu-close-atomic-hide-r364/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-menu-close-atomic-hide-r364/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "3b9f67ea25e65d40cc383e7af319b35bded7083143f3a1efbf2c69c42b48beb2"
)

BANK_SIZE = 0x4000
BANK = 31
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})

MENU_EXIT_ADDR = 0x6CE2
MENU_EXIT_PREIMAGE = bytes.fromhex("E1 F1 AF E0 E4 C3 9A 09")
MENU_EXIT_PATCH = bytes.fromhex("E1 F1 C3 F0 6E 00 00 00")

# r329's wrapper enters under DI, restores its saved A, hides the Window, then
# formerly enabled interrupts immediately before the jump to MENU_EXIT_ADDR.
WRAPPER_TAIL_ADDR = 0x6EE5
WRAPPER_TAIL_PREIMAGE = bytes.fromhex("F1 CB AF E0 40 FB C3 E2 6C")
WRAPPER_TAIL_PATCH = bytes.fromhex("F1 CB AF E0 40 00 C3 E2 6C")

ATOMIC_EXIT_ADDR = 0x6EF0
ATOMIC_EXIT_CAVE_SIZE = 16
ATOMIC_EXIT = bytes.fromhex(
    "AF E0 E4 "       # FFE4=0: relinquish menu ownership
    "F0 40 CB AF E0 40 "  # LCDC.5=0: hide Window with current selectors
    "AF FB C3 9A 09"  # restore native A=0/Z, EI, bank-1 return thunk
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(address: int) -> int:
    require(0x4000 <= address < 0x8000, f"invalid banked address ${address:04X}")
    return BANK * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def checked_output(path: Path, label: str) -> Path:
    resolved, scratch = path.resolve(), TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be below repository tmp/")
    return resolved


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * BANK_SIZE, "r363 base size changed")
    require(digest(source) == BASE_SHA256, f"wrong exact r363 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
            "r363 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(base_receipt.get("schema")
            == "penta-stage1-fast-final-window-selector-r363-build-v1",
            "r363 receipt schema drifted")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r363 receipt names another candidate")

    exit_offset = bank_offset(MENU_EXIT_ADDR)
    wrapper_offset = bank_offset(WRAPPER_TAIL_ADDR)
    cave_offset = bank_offset(ATOMIC_EXIT_ADDR)
    require(source[exit_offset:exit_offset + len(MENU_EXIT_PREIMAGE)]
            == MENU_EXIT_PREIMAGE, "native menu exit preimage changed")
    require(source[wrapper_offset:wrapper_offset + len(WRAPPER_TAIL_PREIMAGE)]
            == WRAPPER_TAIL_PREIMAGE, "menu wrapper tail preimage changed")
    require(source[cave_offset:cave_offset + ATOMIC_EXIT_CAVE_SIZE]
            == bytes([0xFF]) * ATOMIC_EXIT_CAVE_SIZE,
            "atomic menu-exit cave is no longer erased")
    require(len(ATOMIC_EXIT) <= ATOMIC_EXIT_CAVE_SIZE,
            "atomic menu-exit helper exceeds owned cave")

    # The current image has exactly one reviewed transfer to the native close
    # exit: r329's wrapper tail.  This pins the complete incoming edge rather
    # than leaving an unreviewed enabled-IME route into the patched exit.
    transfer = bytes((0xC3,)) + MENU_EXIT_ADDR.to_bytes(2, "little")
    require(source.count(transfer) == 1
            and source.find(transfer) == wrapper_offset + 6,
            "native menu exit transfer census changed")
    # No pre-existing absolute JP/CALL-shaped transfer may already own $6EF0.
    cave_word = ATOMIC_EXIT_ADDR.to_bytes(2, "little")
    for opcode in (0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xD2, 0xD4, 0xDA, 0xDC, 0xCD):
        require(source.count(bytes((opcode,)) + cave_word) == 0,
                "atomic menu-exit cave gained an absolute transfer")

    rom = bytearray(source)
    rom[exit_offset:exit_offset + len(MENU_EXIT_PATCH)] = MENU_EXIT_PATCH
    rom[wrapper_offset:wrapper_offset + len(WRAPPER_TAIL_PATCH)] = WRAPPER_TAIL_PATCH
    rom[cave_offset:cave_offset + len(ATOMIC_EXIT)] = ATOMIC_EXIT
    update_checksums(rom)
    candidate = bytes(rom)

    owned = (
        set(range(exit_offset, exit_offset + len(MENU_EXIT_PATCH)))
        | set(range(wrapper_offset, wrapper_offset + len(WRAPPER_TAIL_PATCH)))
        | set(range(cave_offset, cave_offset + len(ATOMIC_EXIT)))
    )
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(changed <= owned | CHECKSUM_OFFSETS,
            f"r364 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}")
    require(candidate[wrapper_offset + 5] == 0x00,
            "wrapper still enables interrupts before ownership clear")
    require(candidate[cave_offset:cave_offset + len(ATOMIC_EXIT)] == ATOMIC_EXIT,
            "atomic exit helper postimage changed")
    require(ATOMIC_EXIT.index(bytes.fromhex("E0 E4"))
            < ATOMIC_EXIT.index(bytes.fromhex("CB AF E0 40"))
            < ATOMIC_EXIT.index(bytes.fromhex("FB C3 9A 09")),
            "ownership/hide/EI ordering is no longer atomic")

    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-menu-close-atomic-hide-r364-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r363_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "hardware_incident": {
            "platform": "Analogue Pocket",
            "symptoms": [
                "red/green tiles after native menu close",
                "repeated stage strip at screen bottom",
                "gray room tile above Sarah",
            ],
            "root_cause": (
                "r363 enabled IME before FFE4 relinquished menu ownership; "
                "an accepted VBlank could republish the stale Window"
            ),
        },
        "patch": {
            "wrapper": "bank31:$6EEA EI -> NOP",
            "exit": "bank31:$6CE2 -> atomic bank31:$6EF0 helper",
            "order": ["FFE4=0", "LCDC.5=0", "A=0/Z", "EI", "bank1 return"],
            "steady_state_speed_cost": 0,
            "menu_close_only_added_cycles": 56,
        },
        "required_live_gates": base_receipt["required_live_gates"],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(output),
        "status": receipt["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
