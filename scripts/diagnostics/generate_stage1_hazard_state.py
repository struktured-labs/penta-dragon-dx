#!/usr/bin/env python3
"""Generate a ROM-owned, stationary Stage-1 hazard-room savestate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from verify_stage1_north_integrity import detect_publication_boundary


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_stage1_north_integrity.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
TRAJECTORY_HEADER_SIZE = 31
TRAJECTORY_VIEW_SIZE = 21 * 19
TRAJECTORY_RECORD_SIZE = TRAJECTORY_HEADER_SIZE + 2 * TRAJECTORY_VIEW_SIZE
OWNER_STATUS_CGB_OWNED = 1


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--target-camera", type=lambda value: int(value, 0), default=0x015C,
        help="Stage-1 camera coordinate to settle and save (default: 0x015C)",
    )
    parser.add_argument("--target-settle", type=int, default=20)
    parser.add_argument("--min-hazard-cells", type=int, default=1)
    parser.add_argument("--min-tooth-cells", type=int, default=1)
    parser.add_argument(
        "--fire", action="store_true",
        help="hold A while walking north so the fixture includes live combat",
    )
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    output.mkdir(parents=True, exist_ok=True)
    publication = detect_publication_boundary(rom.read_bytes())

    with tempfile.TemporaryDirectory(prefix=".stage1-hazard-", dir=output) as name:
        work = Path(name)
        prefix = work / "north-route"
        prefix.mkdir()
        state = work / "stage1-hazard.ss0"
        environment = os.environ.copy()
        environment.update({
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "STAGE1_NORTH_OUT": str(prefix),
            "STAGE1_NORTH_FRAMES": "3000",
            "STAGE1_NORTH_PLAY_FRAMES": "1800",
            "STAGE1_NORTH_TARGET_ROOM": "1",
            "STAGE1_NORTH_TARGET_CAMERA": str(args.target_camera),
            "STAGE1_NORTH_TARGET_SETTLE": str(args.target_settle),
            "STAGE1_NORTH_STATE_OUT": str(state),
            "STAGE1_NORTH_FIRE": "1" if args.fire else "0",
            "STAGE1_NORTH_PUBLICATION_VARIANT": str(
                publication["variant"]
            ),
            "STAGE1_NORTH_PUBLICATION_PC": str(
                publication["publication_pc_hex"]
            ),
            "STAGE1_NORTH_PUBLICATION_SEGMENT": str(
                publication["publication_segment_hex"]
            ),
            "STAGE1_NORTH_PUBLICATION_PRIMARY_SHA256": str(
                publication["primary_sha256"]
            ),
            "STAGE1_NORTH_PUBLICATION_PRIMARY_HEX": str(
                publication["primary_hex"]
            ),
        })
        log = work / "mgba.log"
        try:
            with log.open("w") as stream:
                completed = subprocess.run(
                    [
                        str(MGBA), "--fastforward",
                        "-C", f"savegamePath={work}",
                        "-C", f"savestatePath={work}",
                        str(rom), "--script", str(PROBE),
                    ],
                    cwd=work,
                    env=environment,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=args.timeout,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            failure_runtime = output / "timeout-runtime"
            shutil.copytree(prefix, failure_runtime, dirs_exist_ok=True)
            shutil.copy2(log, output / "mgba-timeout.log")
            raise RuntimeError(
                f"guarded mGBA timed out; preserved {failure_runtime}"
            ) from None
        meta = prefix / "probe.txt"
        screenshot = prefix / "stage1-hazard.png"
        if completed.returncode != 0 or not state.is_file() or not meta.is_file():
            failure_log = output / "mgba-failure.log"
            shutil.copy2(log, failure_log)
            if meta.is_file():
                shutil.copy2(meta, output / "stage1-hazard-failure.meta")
            raise RuntimeError(
                f"guarded mGBA failed ({completed.returncode}); "
                f"see {failure_log}"
            )
        metadata = meta.read_text()
        camera_text = f"{args.target_camera:04X}"
        required = (
            "status=ok", "final_room=01", f"target_camera={camera_text}",
            "state_saved=1", "final_state=scene:02 room:01 ffc1:01",
            f"dc02:{args.target_camera & 0xFF:02X} "
            f"dc03:{args.target_camera >> 8:02X}",
        )
        missing = [token for token in required if token not in metadata]
        hardware_match = re.search(
            r"final_hardware=hdma5:([0-9A-F]{2}) vbk:([0-9A-F]{2}) "
            r"svbk:([0-9A-F]{2}) lcdc:([0-9A-F]{2})",
            metadata,
        )
        hardware = (
            tuple(int(value, 16) for value in hardware_match.groups())
            if hardware_match is not None else None
        )
        hardware_settled = (
            hardware is not None
            and hardware[0] == 0xFF       # no HBlank/GDMA transfer active
            and hardware[1] == 0x00       # tile-map bank selected
            and hardware[2] == 0x01       # native WRAM/stack bank restored
            and hardware[3] & 0x80 != 0   # rendered gameplay, not LCD-off
        )
        trajectory = (prefix / "trajectory.bin").read_bytes()
        if (
            len(trajectory) < TRAJECTORY_RECORD_SIZE
            or len(trajectory) % TRAJECTORY_RECORD_SIZE
        ):
            raise RuntimeError("generated hazard trajectory is truncated")
        final = trajectory[-TRAJECTORY_RECORD_SIZE:]
        owner_status = final[27]
        owner_room = final[28]
        owner_epoch = final[29] | final[30] << 8
        tiles = final[
            TRAJECTORY_HEADER_SIZE:
            TRAJECTORY_HEADER_SIZE + TRAJECTORY_VIEW_SIZE
        ]
        hazard_cells = sum(0x60 <= tile <= 0x7F for tile in tiles)
        tooth_cells = sum(
            0x64 <= tile <= 0x69 or 0x74 <= tile <= 0x79
            for tile in tiles
        )
        if (
            missing
            or not hardware_settled
            or owner_status != OWNER_STATUS_CGB_OWNED
            or owner_epoch in (0, 0xFFFF)
            or hazard_cells < args.min_hazard_cells
            or tooth_cells < args.min_tooth_cells
            or not screenshot.is_file()
        ):
            raise RuntimeError(
                "generated hazard fixture failed: "
                + ", ".join(
                    missing or [
                        f"hardware={hardware}",
                        f"page_owner={owner_status}/{owner_room:02X}/"
                        f"{owner_epoch:04X}",
                        f"hazard_cells={hazard_cells}",
                        f"tooth_cells={tooth_cells}",
                    ]
                )
            )

        state_out = output / "stage1-hazard.ss0"
        shot_out = output / "stage1-hazard.png"
        meta_out = output / "stage1-hazard.meta"
        state.replace(state_out)
        screenshot.replace(shot_out)
        meta.replace(meta_out)
        receipt = {
            "schema": "penta-stage1-hazard-state-v1",
            "generator_sha256": digest(Path(__file__)),
            "probe_sha256": digest(PROBE),
            "rom": str(rom),
            "rom_sha256": digest(rom),
            "state": str(state_out),
            "state_sha256": digest(state_out),
            "screenshot": str(shot_out),
            "screenshot_sha256": digest(shot_out),
            "hazard_cells": hazard_cells,
            "tooth_cells": tooth_cells,
            "target_camera": args.target_camera,
            "target_settle": args.target_settle,
            "minimum_hazard_cells": args.min_hazard_cells,
            "minimum_tooth_cells": args.min_tooth_cells,
            "fire": args.fire,
            "hardware": {
                "hdma5": hardware[0],
                "vbk": hardware[1],
                "svbk": hardware[2],
                "lcdc": hardware[3],
                "settled": hardware_settled,
            },
            "metadata": metadata.splitlines(),
            "passed": True,
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
    print(
        "PASS: generated current-ROM Stage-1 hazard state "
        f"({hazard_cells} family / {tooth_cells} tooth cells)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
