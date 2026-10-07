#!/usr/bin/env python3
"""Verify YAML-owned item icon colors across every native menu group."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import release_lock_lineage  # noqa: E402
import playtest_successor_lineage  # noqa: E402
from menu_icon_colorization import (  # noqa: E402
    MENU_LUT_OVERRIDES,
    MENU_SEMANTIC_FAMILIES,
    build_menu_lut,
)
PROBE = Path(__file__).with_name("probe_menu_icon_palettes.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
BANK_SIZE = 0x4000
BANK13_LUT = 13 * BANK_SIZE + (0x7000 - 0x4000)
BANK20_LUT = 20 * BANK_SIZE + (0x4100 - 0x4000)
MENU_FIRST_ENTRY = 0x1B48
MENU_WRAPPER_PREFIX = bytes.fromhex("F0 99 F5 3E 14 CD 61 00 CD 00 40")
R441_SHA256 = '44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702'
R442_SHA256 = 'ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46'
TITLE_V5_SHA256 = '6b375a8080df3c982f63a92ea0a679241d8c77cf370776d38bd5b4be8c101e35'
TITLE_V6_R445C_SHA256 = 'baeeb893cf5cd47192273b18eaf9d1bc7902f9ab55da2b3306d2e32db00fcebe'
TITLE_V6_R449F_SHA256 = '15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b'
TITLE_V6_R449F_PREHELPER_SHA256 = 'd82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074'
TITLE_V6_R451C_SHA256 = 'b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892'
R455_SHA256 = '6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9'
R456C_SHA256 = '8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4'
R456D_SHA256 = '69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722'
R527_SHA256 = '13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b'
R528_SHA256 = 'e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50'
R529_SHA256 = '5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208'
R530_SHA256 = '46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30'
R531_SHA256 = '9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855'
R532_SHA256 = '055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821'
R533_SHA256 = '4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba'
R534_SHA256 = '727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b'
R535_TILE_RETIRE_SHA256 = '681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3'
R535_STAGE_CARD_BLACK_SHA256 = 'fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576'
R536_PENTA_SEAM_SHA256 = "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350"
SPIKE_DEATH_SHA256 = "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d"
R535_STAGE1_ONLY_CARD_BLACK_SHA256 = 'b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96'
R536_STAGE1_ONLY_CARD_BLACK_SHA256 = 'ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63'
# These dungeon-only entries are inherited in the private bank-0 menu LUT.
# They are not menu icons. r438's gameplay bank-1 tooth attributes must not
# become a menu oracle. Accept this separation only for the reviewed ROM,
# and independently reject these IDs if any captured menu actually uses one.
MENU_RESERVED_HAZARDS = {
    **{tile: 7 for tile in (*range(0x64, 0x6A), *range(0x74, 0x7A))},
    **{tile: 6 for tile in (0x6B, 0x6F, 0x7B, 0x7F)},
}


def menu_oracle(data: bytes) -> tuple[bytes, frozenset[int]]:
    if playtest_successor_lineage.is_candidate(data):
        # #61: inherit authored expectations only after authenticating the
        # complete delta and proving both tables and entry are unchanged.
        return menu_oracle(playtest_successor_lineage.authenticated_parent(
            data, (BANK13_LUT, BANK13_LUT + 0x100),
            (BANK20_LUT, BANK20_LUT + 0x100),
            (MENU_FIRST_ENTRY, MENU_FIRST_ENTRY + len(MENU_WRAPPER_PREFIX)),
        ))
    from build_sara_atomic_pose import CANDIDATE_SHA as SARA_SHA, authenticated_parent as sara_parent
    if hashlib.sha256(data).hexdigest() == SARA_SHA:
        return menu_oracle(sara_parent(data))
    expected = bytearray(build_menu_lut(data[BANK13_LUT:BANK13_LUT+0x100]))
    reserved = frozenset()
    if hashlib.sha256(data).hexdigest() in {R441_SHA256, R442_SHA256, TITLE_V5_SHA256, TITLE_V6_R445C_SHA256, TITLE_V6_R449F_SHA256, TITLE_V6_R449F_PREHELPER_SHA256, TITLE_V6_R451C_SHA256, R455_SHA256, R456C_SHA256, R456D_SHA256, R527_SHA256, R528_SHA256, R529_SHA256, R530_SHA256, R531_SHA256, R532_SHA256, R533_SHA256, R534_SHA256, R535_TILE_RETIRE_SHA256, R535_STAGE_CARD_BLACK_SHA256, R536_PENTA_SEAM_SHA256, "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b", SPIKE_DEATH_SHA256, R535_STAGE1_ONLY_CARD_BLACK_SHA256, R536_STAGE1_ONLY_CARD_BLACK_SHA256,
        # Release lock: inherits the c693 private bank-20 menu LUT byte-for-byte.
        release_lock_lineage.CANDIDATE_SHA256}:
        reserved = frozenset(MENU_RESERVED_HAZARDS)
        for tile, value in MENU_RESERVED_HAZARDS.items():
            expected[tile] = value
    return bytes(expected), reserved

EXPECTED_GROUPS = ("MEDICAL", "SPECIAL", "PROTECT", "MEDICAL", "SPECIAL")
GROUP_LABEL_TAILS = {
    "MEDICAL": bytes.fromhex("E0 D5 E1 E3 E4 E5 E6 EF"),
    "SPECIAL": bytes.fromhex("EC ED E2 EB EE E5 E6 EF"),
    "PROTECT": bytes.fromhex("E7 E8 E9 EA E2 EB EA EF"),
}


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def row_bytes(report: dict[str, str], page: int, plane: str, row: int) -> bytes:
    value = report.get(f"page{page}_{plane}{row}", "")
    if len(value) != 40:
        raise ValueError(
            f"page {page} {plane} row {row} has {len(value) // 2} cells"
        )
    return bytes.fromhex(value)


def run_probe(rom: Path, output: Path, run_name: str) -> tuple[dict[str, str], list[Path]]:
    runtime = output / f"{run_name}.runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    report_path = output / f"{run_name}.txt"
    report_path.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "MENU_ICON_PALETTE_OUT": str(report_path),
        "MENU_ICON_PALETTE_FRAMES": "1510",
    })
    command = [
        str(MGBA), "--fastforward", str(runtime_rom),
        "--script", str(PROBE), "-C", f"savegamePath={runtime}",
    ]
    try:
        subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True,
            timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    if not report_path.is_file():
        raise RuntimeError(f"{run_name}: no report within 60 seconds")
    screenshots = [
        Path(f"{report_path}.page-{page:02d}.png") for page in range(5)
    ]
    if not all(path.is_file() for path in screenshots):
        raise RuntimeError(f"{run_name}: incomplete screenshot set")
    return parse_report(report_path), screenshots


def audit_report(
    report: dict[str, str], expected_lut: bytes, require_colored: bool,
    forbidden_tiles: frozenset[int] = frozenset(),
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    pages: list[dict[str, object]] = []
    if report.get("pages") != "5":
        failures.append(f"captured {report.get('pages', '0')} pages, expected 5")
    for page in range(5):
        page_mismatches = 0
        tile_mismatches = 0
        colored_cells = 0
        seen_colored_tiles: set[int] = set()
        rows: list[bytes] = []
        try:
            for row in range(6):
                packed = row_bytes(report, page, "packed", row)
                tiles = row_bytes(report, page, "tiles", row)
                attrs = row_bytes(report, page, "attrs", row)
                rows.append(tiles)
                forbidden = sorted(set(tiles) & forbidden_tiles)
                if forbidden:
                    failures.append(f'page {page} row {row} publishes reserved dungeon IDs: {forbidden}')
                tile_mismatches += sum(a != b for a, b in zip(packed, tiles))
                for tile, attr in zip(tiles, attrs):
                    expected = expected_lut[tile]
                    page_mismatches += attr != expected
                    if expected:
                        colored_cells += 1
                        seen_colored_tiles.add(tile)
        except ValueError as error:
            failures.append(str(error))
            continue
        expected_group = EXPECTED_GROUPS[page]
        label_tail = GROUP_LABEL_TAILS[expected_group]
        label_exact = rows[0].endswith(label_tail)
        if not label_exact:
            failures.append(
                f"page {page} does not expose the native {expected_group} label"
            )
        if tile_mismatches:
            failures.append(
                f"page {page} has {tile_mismatches} Window/C4E0 tile mismatches"
            )
        if page_mismatches:
            failures.append(
                f"page {page} has {page_mismatches} canonical palette mismatches"
            )
        pages.append({
            "page": page,
            "expected_group": expected_group,
            "label_tail": label_tail.hex().upper(),
            "label_exact": label_exact,
            "tile_mismatches": tile_mismatches,
            "palette_mismatches": page_mismatches,
            "colored_cells": colored_cells,
            "colored_tile_ids": [f"{tile:02X}" for tile in sorted(seen_colored_tiles)],
        })

        if page == 2:
            visible_tiles = set().union(*[set(row) for row in rows])
            for family, (tiles, palette) in MENU_SEMANTIC_FAMILIES.items():
                if family == "hp_fill":
                    continue
                missing = sorted(set(tiles) - visible_tiles)
                if missing:
                    failures.append(
                        f"PROTECT page misses {family} tiles "
                        + ",".join(f"{tile:02X}" for tile in missing)
                    )
                wrong = [tile for tile in tiles if expected_lut[tile] != palette]
                if wrong:
                    failures.append(
                        f"PROTECT page has incomplete {family} palette ownership"
                    )

    # The populated cold-start MEDICAL page is the release receipt that proves
    # the colored tiles are real icons, rather than only neutral menu chrome.
    medical = pages[0] if pages else {}
    if require_colored and int(medical.get("colored_cells", 0)) < 16:
        failures.append("MEDICAL page exposed fewer than sixteen colored icon cells")
    hp_tiles, hp_palette = MENU_SEMANTIC_FAMILIES["hp_fill"]
    for page in range(min(5, len(pages))):
        attrs = row_bytes(report, page, "attrs", 4)
        tiles = row_bytes(report, page, "tiles", 4)
        hp_cells = [attr for tile, attr in zip(tiles, attrs) if tile in hp_tiles]
        if len(hp_cells) != 15 or any(attr != hp_palette for attr in hp_cells):
            failures.append(
                f"page {page} HP bar is not fifteen complete palette-{hp_palette} "
                "fill cells"
            )
    return failures, {"pages": pages}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--negative-control", action="store_true")
    parser.add_argument(
        "--expect", choices=("auto", "canonical", "neutral"), default="auto",
        help="auto-detect the optional bank-20 publisher, or require a mode",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")

    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = rom.read_bytes()
    if (len(data) != 32 * BANK_SIZE
            and not release_lock_lineage.is_candidate(data)
            and not playtest_successor_lineage.is_candidate(data)):
        print(f"FAIL: expected a 512 KiB ROM, got {len(data)} bytes")
        return 1
    canonical_lut = data[BANK13_LUT:BANK13_LUT + 0x100]
    private_lut = data[BANK20_LUT:BANK20_LUT + 0x100]
    publisher_present = data[
        MENU_FIRST_ENTRY:MENU_FIRST_ENTRY + len(MENU_WRAPPER_PREFIX)
    ] == MENU_WRAPPER_PREFIX
    expected_mode = args.expect
    if expected_mode == "auto":
        expected_mode = "canonical" if publisher_present else "neutral"
    expected_lut, forbidden_tiles = (
        menu_oracle(data) if expected_mode == "canonical"
        else (bytes(0x100), frozenset())
    )
    failures: list[str] = []
    if expected_mode == "canonical" and not publisher_present:
        failures.append("canonical menu publisher is absent from the fixed entry")
    if expected_mode == "neutral" and publisher_present:
        failures.append("neutral mode requested but the canonical publisher is present")
    if expected_mode == "canonical" and private_lut != expected_lut:
        failures.append("bank-20 menu LUT differs from its canonical menu overlay")

    receipts: list[dict[str, object]] = []
    raw_reports: list[dict[str, str]] = []
    for run in range(args.runs):
        report, screenshots = run_probe(rom, output, f"run-{run + 1}")
        run_failures, receipt = audit_report(
            report, expected_lut, expected_mode == "canonical", forbidden_tiles
        )
        failures.extend(f"run {run + 1}: {item}" for item in run_failures)
        receipt.update({
            "run": run + 1,
            "report": str(output / f"run-{run + 1}.txt"),
            "screenshots": [str(path) for path in screenshots],
        })
        receipts.append(receipt)
        raw_reports.append(report)
    if len(raw_reports) > 1 and any(
        report != raw_reports[0] for report in raw_reports[1:]
    ):
        failures.append("A/B emulator reports are not deterministic")

    negative_control: dict[str, object] | None = None
    if args.negative_control:
        if expected_mode != "canonical":
            parser.error("--negative-control requires canonical mode")
        mutated = bytearray(data)
        original = mutated[BANK20_LUT + 0x88]
        mutated[BANK20_LUT + 0x88] = (original + 1) & 7
        negative_rom = output / "negative-control-tile88.gb"
        negative_rom.write_bytes(mutated)
        report, _ = run_probe(negative_rom, output, "negative-control")
        negative_failures, _ = audit_report(report, expected_lut, True, forbidden_tiles)
        caught = bool(negative_failures)
        negative_control = {
            "tile": "88",
            "original_palette": original,
            "mutated_palette": mutated[BANK20_LUT + 0x88],
            "caught": caught,
            "failures": negative_failures,
        }
        if not caught:
            failures.append("negative LUT mutation was not detected")

    manifest = {
        "schema": "penta-menu-icon-palettes-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom),
        "rom_sha256": hashlib.sha256(data).hexdigest(),
        "canonical_lut_sha256": hashlib.sha256(canonical_lut).hexdigest(),
        "forbidden_menu_tile_ids": [f'{tile:02X}' for tile in sorted(forbidden_tiles)],
        "expected_menu_lut_sha256": hashlib.sha256(expected_lut).hexdigest(),
        "expected_mode": expected_mode,
        "publisher_present": publisher_present,
        "private_lut_matches": private_lut == expected_lut,
        "menu_lut_overrides": {
            f"{tile:02X}": palette
            for tile, palette in sorted(MENU_LUT_OVERRIDES.items())
        },
        "runs": receipts,
        "negative_control": negative_control,
        "failures": failures,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    if failures:
        print(f"FAIL: {len(failures)} menu-icon regression(s)")
        return 1
    print("PASS: every menu page is canonical, deterministic, and YAML-owned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
