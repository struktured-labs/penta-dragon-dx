#!/usr/bin/env python3
"""Prove the pickup verifier retries transport crashes without hiding them."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zlib

from PIL import Image

from normalize_mgba_state_pc import (
    GB_STATE_SIZE,
    MBC1_BANK_HI,
    MBC1_BANK_LO,
    MEMORY_CURRENT_BANK,
    normalize,
    png_chunks,
    state_offset,
    write_png,
)
from verify_pickup_live_palettes import run_state


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="penta-pickup-retry-") as name:
        output = Path(name)
        calls = 0

        def crash_then_render(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return subprocess.CompletedProcess(command, -11)
            environment = kwargs["env"]
            Path(environment["PICKUP_LIVE_OUT"]).write_text("frames=180\n")
            Image.new("RGB", (160, 144), "black").save(
                environment["PICKUP_LIVE_SCREENSHOT"]
            )
            return subprocess.CompletedProcess(command, 0)

        pickup = SimpleNamespace(name="Shield", palette=5, tiles=(0x3C,))
        with patch(
            "verify_pickup_live_palettes.subprocess.run",
            side_effect=crash_then_render,
        ):
            result = run_state(
                Path("/fake/mgba"),
                Path("/fake/candidate.gb"),
                Path("shield.ss0"),
                [pickup],
                output,
                1.0,
                18,
                2,
            )

        attempts = result.get("launch_attempts", [])
        checks = {
            "the first synthetic transport crash is retained": (
                len(attempts) == 2
                and attempts[0]["returncode"] == -11
                and not attempts[0]["complete"]
            ),
            "the bounded retry produces a complete native artifact set": (
                attempts[1]["returncode"] == 0
                and attempts[1]["complete"]
                and (output / "shield.png").is_file()
            ),
            "each attempt keeps a distinct diagnostic log": (
                attempts[0]["log"] != attempts[1]["log"]
                and all(Path(item["log"]).is_file() for item in attempts)
            ),
        }

        source_state = output / "bank13-source.ss0"
        explicit_state = output / "bank1-explicit.ss0"
        retained_state = output / "bank13-retained.ss0"
        raw = bytearray(GB_STATE_SIZE)
        raw[MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2] = (13).to_bytes(
            2, "little"
        )
        raw[MBC1_BANK_LO] = 13
        raw[MBC1_BANK_HI] = 0
        raw[state_offset(0xFF99)] = 1
        write_png(
            source_state,
            [(b"gbAs", zlib.compress(bytes(raw))), (b"IEND", b"")],
        )
        normalize(source_state, explicit_state, 0x016C, [], bank=1)
        normalize(source_state, retained_state, 0x016C, [])

        def state_bytes(path: Path) -> bytes:
            payloads = [
                payload for kind, payload in png_chunks(path.read_bytes())
                if kind == b"gbAs"
            ]
            return zlib.decompress(payloads[0])

        explicit = state_bytes(explicit_state)
        retained = state_bytes(retained_state)
        checks.update({
            "explicit pickup-state bank repair updates MBC and FF99 together": (
                int.from_bytes(
                    explicit[
                        MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2
                    ],
                    "little",
                ) == 1
                and explicit[MBC1_BANK_LO] == 1
                and explicit[MBC1_BANK_HI] == 0
                and explicit[state_offset(0xFF99)] == 1
            ),
            "ordinary normalized fixtures retain their captured bank": (
                int.from_bytes(
                    retained[
                        MEMORY_CURRENT_BANK:MEMORY_CURRENT_BANK + 2
                    ],
                    "little",
                ) == 13
                and retained[MBC1_BANK_LO] == 13
            ),
        })
        for description, passed in checks.items():
            print(f"{'PASS' if passed else 'FAIL'}: {description}")
        if not all(checks.values()):
            return 1
    print("PASS: pickup transport retry is bounded, observable, and tested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
