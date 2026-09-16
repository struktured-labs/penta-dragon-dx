#!/usr/bin/env python3
"""Reject the unsafe exact-r264 Stage-7 unpaused-HDMA experiment.

The proposed experiment overlaps one 48-block HBlank DMA attribute transfer
with the native four-tile terrain writer.  It would have to leave VBK=1 at
each HBlank boundary, switch VBK to 0 after the DMA slice, write four tile
IDs, and restore VBK=1 before the following HBlank.

That schedule is not a hardware-qualified experiment:

* the CGB VRAM-DMA contract says not to change the destination VRAM bank
  (FF4F/VBK) while HBlank DMA is active; and
* even before that semantic prohibition, the raw operations have only three
  T-cycles of idealized HBlank+mode-2 margin.  A real post-DMA mode poll makes
  the complete bank-toggle body overrun that interval, while the production
  robust poll makes the fourth tile write itself overrun it.

This audit is deliberately incapable of writing a ROM.  It binds the finding
to the exact visually repaired r264 ROM, checks the relevant production
preimages, exercises mutation controls, and emits a machine-readable blocker
receipt only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"

# Strict exact-r264 preimages.  End addresses are exclusive.
PREIMAGES = (
    ("inline_copier", 1, 0x42A7, 0x435A,
     "ae6ce521529209c6b3cdf553c93b59434e2e2372955143bd6d7a236751c564a1"),
    ("title_pure_entry", 1, 0x435A, 0x4368,
     "57b9502360cdce7fce9d8ff462a2599bfdcb6ecb68c802a904a1e8136d2f442e"),
    ("row_helper_source", 21, 0x4A00, 0x4A79,
     "d28ac08f093c2e6cc065d87c3dedc0e28779dda54885e0ba7f1c6c8ed77804d0"),
    ("row_helper_installer", 21, 0x4900, 0x4924,
     "a7411b17a1333c56c2a0628df87b04a779ef7dd5cc2f05450d40f1fbeba61e5f"),
    ("bank_mapper", 0, 0x0061, 0x0071,
     "f6411122c1e6ae9b63a0682431dbc412902a0f45c809dab526682920034b2622"),
    ("r264_hidden_menu_tail", 1, 0x77A8, 0x77AC,
     "b470820fac2458966a7fe88118cc7665ca204218e36deb292131178669458a6d"),
)

STAGE7_IMMUTABLE_LUT_SHA256 = (
    "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a"
)

# Normal-speed CGB timing in T-cycles/dots.
MIN_HBLANK_T = 87
MODE2_T = 80
HDMA_16_BYTES_T = 32                 # 8 M-cycles
STOCK_TILE_CELL_T = 24               # LD A,[DE]; INC DE; LD [HL+],A
STOCK_FOUR_TILES_T = 4 * STOCK_TILE_CELL_T
VBK_ZERO_T = 16                      # XOR A; LDH [VBK],A
VBK_ONE_T = 20                       # LD A,1; LDH [VBK],A
ROBUST_MODE0_EXIT_T = 28             # LDH A,[STAT]; AND 3; JR NZ (not taken)
OPTIMISTIC_MODE0_EXIT_T = 20         # LDH A,[C]; RRA; JR C (not taken)

PANDOCS_SOURCE = (
    "https://github.com/gbdev/pandocs/blob/master/src/CGB_Registers.md"
    "#bit-7--1--hblank-dma"
)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank == 0:
        if not 0 <= address < 0x4000:
            raise AssertionError((bank, address))
        return address
    if not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * 0x4000 + address - 0x4000


def require_preimages(payload: bytes) -> list[dict[str, object]]:
    checked = []
    for name, bank, start, end, expected_sha in PREIMAGES:
        offset = bank_offset(bank, start)
        blob = payload[offset:offset + end - start]
        actual_sha = sha256(blob)
        if actual_sha != expected_sha:
            raise AssertionError(
                f"{name} preimage changed at bank{bank}:${start:04X}-"
                f"${end - 1:04X}: {actual_sha} != {expected_sha}"
            )
        checked.append({
            "name": name,
            "bank": bank,
            "range": f"${start:04X}-${end - 1:04X}",
            "length": end - start,
            "sha256": actual_sha,
        })
    return checked


def require_hdma_schedule(*, active: bool, vbk_changes: int,
                          start_mode: int) -> None:
    if start_mode == 0:
        raise AssertionError("HBlank DMA must not be started in mode 0")
    if start_mode != 3:
        raise AssertionError("bounded proposal requires an exact mode-3 start")
    if active and vbk_changes:
        raise AssertionError(
            "FF4F/VBK cannot change while HBlank DMA remains active"
        )


@dataclass(frozen=True)
class Timing:
    name: str
    hdma: int
    post_dma_poll: int
    vbk_zero: int
    four_tiles: int
    vbk_one: int
    available_hblank_plus_mode2: int

    @property
    def tile_write_complete(self) -> int:
        return self.hdma + self.post_dma_poll + self.vbk_zero + self.four_tiles

    @property
    def body_complete(self) -> int:
        return self.tile_write_complete + self.vbk_one

    def record(self) -> dict[str, object]:
        result = asdict(self)
        result.update({
            "tile_write_complete_t": self.tile_write_complete,
            "tile_write_margin_t": (
                self.available_hblank_plus_mode2 - self.tile_write_complete
            ),
            "body_complete_t": self.body_complete,
            "body_margin_t": (
                self.available_hblank_plus_mode2 - self.body_complete
            ),
        })
        return result


def timing_contract() -> dict[str, object]:
    available = MIN_HBLANK_T + MODE2_T
    raw = Timing(
        "raw_primitives_without_a_post_dma_detector",
        HDMA_16_BYTES_T, 0, VBK_ZERO_T, STOCK_FOUR_TILES_T, VBK_ONE_T,
        available,
    )
    optimistic = Timing(
        "optimistic_bit0_poll",
        HDMA_16_BYTES_T, OPTIMISTIC_MODE0_EXIT_T,
        VBK_ZERO_T, STOCK_FOUR_TILES_T, VBK_ONE_T, available,
    )
    production = Timing(
        "production_robust_mode0_poll",
        HDMA_16_BYTES_T, ROBUST_MODE0_EXIT_T,
        VBK_ZERO_T, STOCK_FOUR_TILES_T, VBK_ONE_T, available,
    )

    # The arithmetic that makes the proposal attractive is real, but it omits
    # any executable way to learn that the DMA slice has fired.
    if raw.body_complete != 164 or raw.body_complete >= available:
        raise AssertionError(raw.record())
    # The most aggressive viable poll leaves only three dots for the final
    # tile access and cannot restore VBK before mode 3.
    if optimistic.tile_write_complete != 164:
        raise AssertionError(optimistic.record())
    if optimistic.tile_write_complete >= available:
        raise AssertionError(optimistic.record())
    if optimistic.body_complete <= available:
        raise AssertionError("optimistic complete body unexpectedly fits")
    # Keeping r264's robust poll makes the fourth tile itself unsafe.
    if production.tile_write_complete <= available:
        raise AssertionError("production polling unexpectedly fits")

    return {
        "units": "normal-speed CGB T-cycles/dots",
        "minimum_hblank_t": MIN_HBLANK_T,
        "mode2_t": MODE2_T,
        "available_hblank_plus_mode2_t": available,
        "models": [raw.record(), optimistic.record(), production.record()],
        "conclusion": (
            "Only the detector-free arithmetic fits as a complete body. "
            "An executable optimized detector leaves 3T before the VRAM "
            "lock for tile writes and restores VBK 17T into mode 3; the "
            "production robust detector makes tile writes overrun by 5T."
        ),
    }


def mutation_controls(payload: bytes) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    for name, bank, start, _end, _digest in PREIMAGES:
        mutant = bytearray(payload)
        mutant[bank_offset(bank, start)] ^= 0x01
        try:
            require_preimages(bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            raise AssertionError(f"mutated {name} escaped its preimage gate")

    for name, values in (
        ("active_vbk_switch_rejected", (True, 2, 3)),
        ("mode0_start_rejected", (False, 0, 0)),
        ("mode2_start_rejected", (False, 0, 2)),
    ):
        try:
            require_hdma_schedule(
                active=values[0], vbk_changes=values[1], start_mode=values[2]
            )
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"negative control {name} unexpectedly passed")

    require_hdma_schedule(active=True, vbk_changes=0, start_mode=3)
    controls["active_fixed_vbk_control_passed"] = True
    return controls


def audit(payload: bytes) -> dict[str, object]:
    digest = sha256(payload)
    if digest != BASE_SHA256:
        raise AssertionError(f"not exact repaired r264: {digest}")
    preimages = require_preimages(payload)
    timings = timing_contract()
    controls = mutation_controls(payload)

    # This call is the design itself and must remain a failing control.
    try:
        require_hdma_schedule(active=True, vbk_changes=2, start_mode=3)
    except AssertionError as exc:
        hardware_blocker = str(exc)
    else:
        raise AssertionError("unsafe unpaused VBK schedule was accepted")

    return {
        "schema": "penta-stage7-unpaused-hdma-r264-static-blocker-v1",
        "status": "BLOCKED_NO_ROM",
        "promotable": False,
        "emulator_run": False,
        "rom_emitted": False,
        "base_sha256": digest,
        "stage_gate": "$D880 == $08 only (design requirement; no patch emitted)",
        "planned_attribute_source": {
            "buffer": "SVBK3:$D000-$D2FF, 24 padded 32-byte rows",
            "compiler": "all 576 exact immutable LUT outputs before publication",
            "immutable_stage7_lut_sha256": STAGE7_IMMUTABLE_LUT_SHA256,
            "dma": "one 48-block HBlank DMA to exact tagged $FFA5 destination",
        },
        "strict_r264_preimages": preimages,
        "timing": timings,
        "hardware_contract": {
            "source": PANDOCS_SOURCE,
            "hdma_block": "16 bytes; CPU halted for about 8 M-cycles / 32T",
            "destination_bank_rule": (
                "Do not change FF4F/VBK until HBlank DMA completes; pause "
                "the transfer while switching banks."
            ),
            "proposed_active_vbk_changes_per_block": 2,
            "blocker": hardware_blocker,
        },
        "mutation_controls": controls,
        "decision": (
            "Do not build or emulator-run this unpaused design.  Pausing and "
            "rearming around each tile group is the already-slow r139 family; "
            "a safe successor must avoid active-DMA VBK changes, for example "
            "by publishing both planes through DMA or by using a non-HDMA "
            "sparse attribute transport."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path(
            "tmp/stage7-unpaused-hdma-pipeline-r264/blocker-receipt.json"
        ),
    )
    args = parser.parse_args()
    receipt = audit(args.base.read_bytes())
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
