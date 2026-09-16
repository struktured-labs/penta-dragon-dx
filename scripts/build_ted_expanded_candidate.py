#!/usr/bin/env python3
"""Reproducibly build production plus the collision-free cached Ted bank."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_v302_title_fix.py"
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
from prototype_ted_expanded_bank import (  # noqa: E402
    combine,
    global_checksum,
    header_checksum,
)
import build_v302_title_fix as production_build  # noqa: E402
from menu_icon_colorization import install_menu_icon_colorization  # noqa: E402
from stage1_hazard_semantic_row import install as install_hazard_row  # noqa: E402
from stage1_room03_fast import install as install_stage1_room03_fast  # noqa: E402
from stage1_split_phase_key import install as install_stage1_split_phase_key  # noqa: E402
from stage1_stale_window_cleanup import install as install_stage1_stale_window_cleanup  # noqa: E402
from stage5_wide_copy import install as install_stage5_wide_copy  # noqa: E402
from stage7_service_guard import install as install_stage7_service_guard  # noqa: E402
from stage_card_palette_handoff import (  # noqa: E402
    install_stage_card_palette_handoff,
)


# The receipt-qualified r8 private Ted payload predates a later source merge
# that silently rearranged several generated fragments in payload-only bank
# 13.  The production build is unaffected, but copying the rearranged bank to
# private bank 16 stalls the deterministic Ted state.  Keep these code-only
# replacements preimage-locked so palette YAML bytes remain rebuildable and a
# future layout change fails here instead of producing another mystery ROM.
TED_PAYLOAD_R8_CODE_FIXUPS = (
    (0x354F2, bytes.fromhex("e11213cd30580520ebe10c79fe0e20b6cd9e53cde55c3e01"), bytes.fromhex("fe0e20b6cd9e53cde55c3e01e070e1d1c1fa0bdce6010707")),
    (0x356FF, bytes.fromhex("e070e1d1c1fa0bdce6010707c69b672e"), bytes.fromhex("c69b672e003e01bffbc3ca7600000000")),
    (0x35710, bytes.fromhex("3e01bffbc3ca76"), bytes.fromhex("00000000000000")),
    (0x357D6, bytes.fromhex("e3"), bytes.fromhex("d7")),
    (0x358F7, bytes.fromhex("dd"), bytes.fromhex("d1")),
    (0x35903, bytes.fromhex("11"), bytes.fromhex("0e")),
    (0x35910, bytes.fromhex("00d80e1006103e77223c223e"), bytes.fromhex("1006103e77223c22000520f7")),
    (0x3591D, bytes.fromhex("12133c12130520f106103e79223c223e0712133d121305"), bytes.fromhex("103e79223c22000520f70d20e7cdab763e02e0a80e0021")),
    (0x35DCC, bytes.fromhex("20f10d20db3e02e0a80e0021bb792a472a90e5f5fa07d780d604e61f5ffa06d78147e607"), bytes.fromhex("bb792a472a90e5f5fa07d780d604e61f5ffa06d78147e6070707070707836f780f0f0fe6")),
    (0x35E2C, bytes.fromhex("0707070707836f780f0f0fe603c6d067545d7ac60857f147f0a8223ce0a83de56f26767e"), bytes.fromhex("03c6d067545d7ac60857f147f0a8223ce0a83de56f26767ee11213cd30580520ebe10c79")),
    (0x3623C, bytes.fromhex("2afe7bda4e6dfe87d24e6dcd8776c34e6d"), bytes.fromhex("2108d734cb66ca4e6dc387760000000000")),
    (0x36530, bytes.fromhex("21a0c106180e18c33c62"), bytes.fromhex("c33c6200000000000000")),
    (0x36D4E, bytes.fromhex("0dc23c620e1805c23c62e1d1c1c9"), bytes.fromhex("e1d1c1c900000000000000000000")),
    (0x37687, bytes.fromhex("ea0ad7fe7cc8fe7ec8fe7fc8fe81c8fa06d7802f3cc618e61f57fa07d7812f3cc618e61f5f7bc603e61ffe0430167a3dfe0f3810fa0ad7fe83201e7afe1020197bb720"), bytes.fromhex("3e84ea0ad7111d05cd90583e86ea0ad7110605cd90583e83ea0ad7111d0acd9058c34e6d2100d80e1006103e06223c223d0520f906103e07223d223c0520f90d20e7c9")),
    (0x376E1, bytes.fromhex("fa1fd7fe16d0c39058"), bytes.fromhex("000000000000000000")),
)

# The old qualifier also rewrote the shared later-stage cache runtime at
# $37BBF-$37C75.  Production now emits the receipt-qualified runtime directly,
# including its additional collision discriminator, so applying the legacy
# overlay would both reject the new fixed-width layout and silently remove the
# new sample.  Keep only the genuinely Ted-private fragment fixups above.


def qualify_ted_payload(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    for offset, expected, replacement in TED_PAYLOAD_R8_CODE_FIXUPS:
        actual = bytes(payload[offset:offset + len(expected)])
        if actual == replacement:
            # Current source may already emit the receipt-qualified form.
            # Retain the same strict two-preimage contract so this remains
            # deterministic and still rejects any unreviewed third variant.
            continue
        if actual != expected:
            raise AssertionError(
                f"Ted payload preimage changed at 0x{offset:05X}: "
                f"expected unqualified {expected.hex()} or qualified "
                f"{replacement.hex()}, got {actual.hex()}"
            )
        if len(expected) != len(replacement):
            raise AssertionError(f"Ted payload fixup changes width at 0x{offset:05X}")
        payload[offset:offset + len(replacement)] = replacement
    path.write_bytes(payload)
    print(
        "qualified private Ted payload: restored Ted-private r8 fragments; "
        "YAML palette ranges remain generated"
    )


def run_builder(arguments: list[str], env: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, str(BUILDER), *arguments],
        cwd=ROOT,
        env=env,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--palette-yaml", type=Path)
    parser.add_argument(
        "--native-sparse",
        action="store_true",
        help=(
            "retain Ted's native sparse/tentacle publication instead of "
            "the diagnostic canonical-limb replacement"
        ),
    )
    parser.add_argument(
        "--native-pose-table",
        action="store_true",
        help="publish exact measured native poses from a bounded bank-17 lookup",
    )
    parser.add_argument(
        "--menu-icon-colors",
        action="store_true",
        help=(
            "install the isolated bank-20 native item-menu attribute "
            "publisher after combining the qualified production image"
        ),
    )
    parser.add_argument(
        "--stage-card-palette-handoff",
        action="store_true",
        help=(
            "load Stage-1 BG0 at the exact native map flip so neither the "
            "outgoing STAGE card nor the first dungeon frame is recolored"
        ),
    )
    parser.add_argument(
        "--stage1-native-gold",
        action="store_true",
        help=(
            "use byte-exact native Stage-1 terrain publication and the "
            "zero-runtime reserved-gold pickup art profile"
        ),
    )
    parser.add_argument(
        "--stage5-wide-copy",
        action="store_true",
        help=(
            "with --stage1-native-gold, route only Stage 5 through the "
            "receipt-proven five-tile native copier"
        ),
    )
    parser.add_argument(
        "--stage7-pure-six",
        action="store_true",
        help=(
            "with --stage1-native-gold, route Stage 7 LCD-on pure tile "
            "publications through the receipt-proven six-tile copier"
        ),
    )
    parser.add_argument(
        "--stage7-fused-dirty",
        action="store_true",
        help=(
            "with --stage7-pure-six, fuse Stage 7 dirty tile and attribute "
            "publication in the private bank-23 helper"
        ),
    )
    parser.add_argument(
        "--stage7-service-guard",
        action="store_true",
        help=(
            "with --stage7-pure-six and --menu-icon-colors, skip the "
            "non-owning death and Stage-1 art VBlank services in scene $08"
        ),
    )
    parser.add_argument(
        "--stage1-precomputed-attrs",
        action="store_true",
        help=(
            "use the accepted native-width Stage-1 copier with cached "
            "precomputed attributes and the post-copy hazard publisher"
        ),
    )
    parser.add_argument(
        "--minimal-prelude",
        action="store_true",
        help="diagnostically retain only scene detection in the VBlank prelude",
    )
    parser.add_argument(
        "--stage1-private-scanner-guard",
        action="store_true",
        help=(
            "diagnostically skip the private Stage-1 hazard scanner in "
            "later-stage scenes"
        ),
    )
    parser.add_argument(
        "--stage1-wram-scene-guard",
        action="store_true",
        help=(
            "diagnostically reject later-stage Stage-1 scanner work and "
            "clear its consumed dirty latch in always-mapped WRAM"
        ),
    )
    parser.add_argument(
        "--stage1-tagged-destination",
        action="store_true",
        help=(
            "use the receipt-qualified exact physical-map destination tag "
            "for Stage-1 pure and dirty publications"
        ),
    )
    parser.add_argument(
        "--stage1-room03-fast",
        action="store_true",
        help=(
            "skip the empty semantic scanner only in exact Stage-1 scene "
            "$02 room $03, retaining every other scanner/repair route"
        ),
    )
    parser.add_argument(
        "--stage1-split-phase-key",
        action="store_true",
        help=(
            "keep Stage-1 semantic content and native source phase in "
            "independent per-map cache bytes"
        ),
    )
    parser.add_argument(
        "--stage1-stale-window-cleanup",
        action="store_true",
        help=(
            "hide orphaned Stage-1 hardware Windows while preserving the "
            "normal VBlank phase"
        ),
    )
    parser.add_argument(
        "--work", type=Path, default=ROOT / "tmp/ted-expanded-build"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)

    production = work / "production.gb"
    production_base = work / "production.base.gb"
    payload = work / "ted-payload.gb"
    payload_base = work / "ted-payload.base.gb"
    clean_env = os.environ.copy()
    for name in (
        "PENTA_TED_CACHED_FULL_PLANE",
        "PENTA_TED_CACHED_SPARSE",
        "PENTA_TED_CACHED_CANONICAL_LIMBS",
        "PENTA_TED_EXPANDED_PAYLOAD",
        "PENTA_TED_EXPANDED_PRODUCTION",
        "PENTA_STAGE_CARD_CLEAN_HANDOFF",
        "PENTA_STAGE_CARD_PALETTE_HANDOFF",
    ):
        clean_env.pop(name, None)
    palette_args = (
        ["--palette-yaml", str(args.palette_yaml.resolve())]
        if args.palette_yaml is not None else []
    )
    production_env = clean_env | {
        # The combined image redirects Ted into the private expanded-bank
        # payload.  Keep production bank 13's complete Angela LUT byte-exact;
        # its receipt-proven neutral tail is borrowed only inside bank 16.
        "PENTA_TED_EXPANDED_PRODUCTION": "1",
        "PENTA_STAGE_CARD_PALETTE_HANDOFF": (
            "1" if args.stage_card_palette_handoff else "0"
        ),
        "PENTA_STAGE_CARD_CLEAN_HANDOFF": (
            "1" if args.stage_card_palette_handoff else "0"
        ),
    }
    if args.stage1_native_gold and args.stage1_precomputed_attrs:
        parser.error(
            "--stage1-native-gold and --stage1-precomputed-attrs are "
            "mutually exclusive"
        )
    if args.stage5_wide_copy and not args.stage1_native_gold:
        parser.error("--stage5-wide-copy requires --stage1-native-gold")
    if args.stage7_pure_six and not args.stage1_native_gold:
        parser.error("--stage7-pure-six requires --stage1-native-gold")
    if args.stage7_fused_dirty and not args.stage7_pure_six:
        parser.error("--stage7-fused-dirty requires --stage7-pure-six")
    if args.stage7_service_guard and not args.stage7_pure_six:
        parser.error("--stage7-service-guard requires --stage7-pure-six")
    if args.stage7_service_guard and not args.menu_icon_colors:
        parser.error("--stage7-service-guard requires --menu-icon-colors")
    stage1_args = (
        [
            "--buffered-stage1-attrs",
            "--reserved-pickup-gold",
        ]
        if args.stage1_native_gold
        else ["--cached-stage1-attrs"]
        if args.stage1_precomputed_attrs
        else [
            # The accepted production lineage uses the 190-byte postcomputed
            # copier. The native-gold release profile above is the fail-safe
            # terrain path selected after the Pocket Stage-1 regression.
            "--buffered-stage1-attrs",
        ]
    )
    run_builder(
        [
            *palette_args,
            *stage1_args,
            *(
                ["--stage1-tagged-destination"]
                if args.stage1_tagged_destination else []
            ),
            *(["--minimal-prelude"] if args.minimal_prelude else []),
            "--output", str(production),
            "--base-output", str(production_base),
        ],
        production_env,
    )
    payload_env = clean_env | {
        "PENTA_TED_CACHED_FULL_PLANE": "1",
        "PENTA_TED_CACHED_SPARSE": "1",
        "PENTA_TED_CACHED_CANONICAL_LIMBS": (
            "0" if args.native_sparse else "1"
        ),
        "PENTA_TED_EXPANDED_PAYLOAD": "1",
    }
    run_builder(
        [
            *palette_args,
            "--stock-tile-copy",
            "--native-room-writers",
            "--output", str(payload),
            "--base-output", str(payload_base),
        ],
        payload_env,
    )
    qualify_ted_payload(payload)
    combine(
        production, payload, output,
        native_pose_table=args.native_pose_table,
        # Stage 1 is redirected only after expansion. Keep the canonical DX
        # copier/death layout here for every later-stage semantic publisher.
        native_stage1_profile=False,
        stage1_private_scanner_guard=args.stage1_private_scanner_guard,
        stage1_wram_scene_guard=args.stage1_wram_scene_guard,
        # Receipt-qualified v78 cadence: exact Shalamar repeats whose raw key
        # ends in zero retain the native tile/sanitizer path.  Omitting this
        # rebuilt the older bank-20 helper and invalidated the accepted boss
        # timing lineage even though every Ted-specific bank stayed exact.
        shalamar_native_exact_class=0,
        # Bank 14 contains native layout data as well as the Stage-1 helper
        # image. Preserve the native bank byte-for-byte and relocate the
        # patched Stage-1 image to the dedicated expansion bank.
        native_layout_rom=ROOT / "rom/Penta Dragon (J).gb",
    )
    if args.stage1_native_gold:
        rom = bytearray(output.read_bytes())
        report = install_stage5_wide_copy(
            rom,
            stage5_wide=args.stage5_wide_copy,
            stage7_pure_six=args.stage7_pure_six,
            stage7_fused_dirty=args.stage7_fused_dirty,
        )
        rom[0x014D] = header_checksum(rom)
        checksum = global_checksum(rom)
        rom[0x014E] = checksum >> 8
        rom[0x014F] = checksum & 0xFF
        output.write_bytes(rom)
        print(
            "installed stage-private copy router: "
            f"Stage 1 native=bank {report.native_stage1_bank}, "
            f"router=bank {report.router_bank}:${report.router:04X}, "
            f"Stage 5 windows={report.windows_per_publication}, "
            f"Stage 7 pure windows={report.stage7_pure_windows}, "
            f"Stage 7 dirty windows={report.stage7_dirty_windows}, "
            f"Stage 7 fused=${report.stage7_fused_entry or 0:04X}"
        )
    rom = bytearray(output.read_bytes())
    hazard_report = install_hazard_row(rom)
    room03_report = None
    if args.stage1_room03_fast:
        room03_report = install_stage1_room03_fast(rom)
    rom[0x014D] = header_checksum(rom)
    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    output.write_bytes(rom)
    print(
        "installed semantic Stage-1 hazard row writer: "
        f"bank {hazard_report['bank']} ${hazard_report['entry']:04X}, "
        f"helper={hazard_report['helper_size']} bytes, "
        f"LUT={hazard_report['lut_size']} bytes"
    )
    if room03_report is not None:
        print(
            "installed Stage-1 room-$03 empty-scanner fast path: "
            f"bank {room03_report['bank']} "
            f"${room03_report['gate_address']:04X}, all other rooms -> "
            f"${room03_report['scanner_address']:04X}"
        )
    if args.menu_icon_colors:
        rom = bytearray(output.read_bytes())
        report = install_menu_icon_colorization(
            rom, production_build.build_colorize_prelude()
        )
        rom[0x014D] = header_checksum(rom)
        checksum = global_checksum(rom)
        rom[0x014E] = checksum >> 8
        rom[0x014F] = checksum & 0xFF
        output.write_bytes(rom)
        print(
            "installed expanded-bank item-menu icon colors: "
            f"bank {report['helper_bank']} ${report['helper_entry']:04X}, "
            f"helper={report['helper_size']} bytes, "
            f"canonical LUT={report['lut_size']} bytes, "
            f"prelude delta={report['prelude_changed_bytes']} bytes"
        )
    if args.stage7_service_guard:
        rom = bytearray(output.read_bytes())
        report = install_stage7_service_guard(rom)
        rom[0x014D] = header_checksum(rom)
        checksum = global_checksum(rom)
        rom[0x014E] = checksum >> 8
        rom[0x014F] = checksum & 0xFF
        output.write_bytes(rom)
        print(
            "installed Stage-7 VBlank owner guards: "
            f"death=${report.death_guard:04X}, "
            f"art=${report.art_guard:04X}, "
            f"menu delay={report.guarded_menu_delay_cycles} cycles"
        )
    if args.stage_card_palette_handoff:
        rom = bytearray(output.read_bytes())
        report = install_stage_card_palette_handoff(rom)
        rom[0x014D] = header_checksum(rom)
        checksum = global_checksum(rom)
        rom[0x014E] = checksum >> 8
        rom[0x014F] = checksum & 0xFF
        output.write_bytes(rom)
        print(
            "installed exact Stage-card palette handoff: "
            f"hook=${report.hook_address:04X}, "
            f"bridge=${report.bridge_address:04X}, "
            f"bank {report.private_bank} ${report.private_entry:04X}, "
            f"helper={report.helper_size} bytes, "
            f"BG0={report.stage1_bg0}, "
            f"discriminator[{report.discriminator_index}]="
            f"${report.title_discriminator:02X}"
        )
    if args.stage1_split_phase_key:
        rom = bytearray(output.read_bytes())
        report = install_stage1_split_phase_key(rom)
        rom[0x014D] = header_checksum(rom)
        checksum = global_checksum(rom)
        rom[0x014E] = checksum >> 8
        rom[0x014F] = checksum & 0xFF
        output.write_bytes(rom)
        print(
            "installed independent Stage-1 content/phase cache: "
            f"bank {report.private_bank} ${report.private_entry:04X}, "
            f"helper={report.helper_size} bytes, "
            f"semantic={report.semantic_key}, phase={report.phase_key}"
        )
    if args.stage1_stale_window_cleanup:
        rom = bytearray(output.read_bytes())
        report = install_stage1_stale_window_cleanup(rom)
        rom[0x014D] = header_checksum(rom)
        checksum = global_checksum(rom)
        rom[0x014E] = checksum >> 8
        rom[0x014F] = checksum & 0xFF
        output.write_bytes(rom)
        print(
            "installed phase-balanced stale Stage-1 Window cleanup: "
            f"branch=${report.branch_address:04X}, "
            f"helper=${report.helper_address:04X}, "
            f"normal={report.normal_cycles_after}T"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
