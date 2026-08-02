#!/usr/bin/env python3
"""Prove the pickup verifier retries transport crashes without hiding them."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

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
        for description, passed in checks.items():
            print(f"{'PASS' if passed else 'FAIL'}: {description}")
        if not all(checks.values()):
            return 1
    print("PASS: pickup transport retry is bounded, observable, and tested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
