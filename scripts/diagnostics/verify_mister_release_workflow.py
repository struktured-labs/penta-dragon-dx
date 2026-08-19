#!/usr/bin/env python3
"""Exercise MiSTer release fail-closed behavior without contacting hardware."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/mister.py"


def load_mister_module():
    spec = importlib.util.spec_from_file_location("penta_mister_release_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_runtime_error(callable_value, message: str) -> None:
    try:
        callable_value()
    except RuntimeError:
        return
    raise AssertionError(message)


def main() -> int:
    mister = load_mister_module()
    local_tmp = ROOT / "tmp"
    local_tmp.mkdir(exist_ok=True)

    # A core mismatch must abort. The older workflow only printed a warning.
    mister.ssh = lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    mister.mister_cmd = lambda *_args, **_kwargs: None
    mister.time.sleep = lambda *_args, **_kwargs: None
    mister.get_corename = lambda: "GAMEBOY"
    expect_runtime_error(
        mister.cmd_launch,
        "cmd_launch accepted a non-GBC core",
    )
    print("PASS: wrong MiSTer core aborts the release launch")

    # A screenshot command that creates no new file must not recycle a stale
    # screenshot from either of the two historical output directories.
    mister.get_corename = lambda: "GBC"
    mister.ssh = lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout="stale.png\n", stderr=""
    )
    if mister.cmd_screenshot("stale-regression") is not None:
        raise AssertionError("stale MiSTer screenshot was accepted as new evidence")
    print("PASS: stale screenshot fallback is rejected")

    if not mister.LOCAL_ROM.is_file() or not mister.LOCAL_RELEASE_PATCH.is_file():
        raise AssertionError("release ROM/IPS missing for local workflow test")
    local_md5 = mister.md5_file(mister.LOCAL_ROM)

    with tempfile.TemporaryDirectory(
        prefix="penta-mister-release-", dir=local_tmp
    ) as temp:
        temp_path = Path(temp)
        emulator_path = temp_path / "emulator-manifest.json"
        emulator_path.write_text('{"test":"hash binding only"}\n')
        screenshot = temp_path / "checkpoint.png"
        screenshot.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\rIHDR"
            + b"\x00\x00\x00\xa0\x00\x00\x00\x90"
        )

        checkpoints = [
            {"name": name, "status": "pending"}
            for name in mister.REQUIRED_HARDWARE_CHECKPOINTS
        ]
        for name in ("gbc_core", "deployed_rom_hash"):
            next(item for item in checkpoints if item["name"] == name)[
                "status"
            ] = "passed"

        hardware_path = temp_path / "hardware-manifest.json"
        hardware = {
            "schema": "penta-dragon-dx-mister-release-v1",
            "status": "hardware-sweep-incomplete",
            "mister_host": mister.MISTER_HOST,
            "rom_md5": local_md5,
            "rom_sha256": mister.sha256_file(mister.LOCAL_ROM),
            "release_patch_sha256": mister.sha256_file(
                mister.LOCAL_RELEASE_PATCH
            ),
            "emulator_manifest": str(emulator_path),
            "emulator_manifest_sha256": mister.sha256_file(emulator_path),
            "checkpoints": checkpoints,
        }
        hardware_path.write_text(json.dumps(hardware))

        mister.require_mister_reservation = lambda: None
        mister.get_corename = lambda: "GBC"
        mister.get_rom_md5 = lambda: local_md5
        expect_runtime_error(
            lambda: mister.cmd_release_sweep_finish(str(hardware_path)),
            "incomplete physical checkpoints were accepted",
        )
        print("PASS: incomplete physical checkpoint set cannot be sealed")

        for item in hardware["checkpoints"]:
            item["status"] = "passed"
            if item["name"] not in {"gbc_core", "deployed_rom_hash"}:
                item["evidence"] = {
                    "screenshot": str(screenshot),
                    "screenshot_sha256": mister.sha256_file(screenshot),
                }
        hardware_path.write_text(json.dumps(hardware))
        mister.cmd_release_sweep_finish(str(hardware_path))
        sealed = json.loads(hardware_path.read_text())
        if sealed.get("status") != "hardware-pass":
            raise AssertionError("complete hardware sweep did not seal")
        print("PASS: exact hash-bound, fully confirmed checkpoint set can seal")

    print("PASS: no MiSTer connection was attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
