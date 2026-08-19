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
    (0x37BBF, bytes.fromhex("afc1"), bytes.fromhex("5cc3")),
    (0x37BC3, bytes.fromhex("f3c1"), bytes.fromhex("35c2")),
    (0x37BC8, bytes.fromhex("86c2"), bytes.fromhex("b3c1")),
    (0x37BCD, bytes.fromhex("9a"), bytes.fromhex("9b")),
    (0x37BCF, bytes.fromhex("4ffaf1c2a9"), bytes.fromhex("a847faa0c1")),
    (0x37BD6, bytes.fromhex("51c3"), bytes.fromhex("dbc1")),
    (0x37BDA, bytes.fromhex("1ab8201313"), bytes.fromhex("faedc2a94f")),
    (0x37C4D, bytes.fromhex("b9"), bytes.fromhex("b8")),
    (0x37C4F, bytes.fromhex("0d"), bytes.fromhex("13")),
    (0x37C52, bytes.fromhex("6ff0bdbd2004e1d1c1c91b1b781213791213f0bd123e01e0e0e1d1c1c90000000000"), bytes.fromhex("b9200d131a6ff0bdbd2004e1d1c1c91b1b781213791213f0bd123e01e0e0e1d1c1c9")),
)


def qualify_ted_payload(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    for offset, expected, replacement in TED_PAYLOAD_R8_CODE_FIXUPS:
        actual = bytes(payload[offset:offset + len(expected)])
        if actual != expected:
            raise AssertionError(
                f"Ted payload preimage changed at 0x{offset:05X}: "
                f"expected {expected.hex()}, got {actual.hex()}"
            )
        if len(expected) != len(replacement):
            raise AssertionError(f"Ted payload fixup changes width at 0x{offset:05X}")
        payload[offset:offset + len(replacement)] = replacement
    path.write_bytes(payload)
    print(
        "qualified private Ted payload: restored r8 code fragments; "
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
    }
    run_builder(
        [
            *palette_args,
            # The accepted production lineage uses the 190-byte postcomputed
            # copier.  The newer 198-byte precomputed prototype consumes the
            # bank-1 tail reserved by the source-built atomic return wrapper.
            "--buffered-stage1-attrs",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
