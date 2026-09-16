#!/usr/bin/env python3
"""Resolve and attest the ROM used by the guarded headed mGBA launcher.

The successful CLI writes only the resolved ROM path to stdout so
``launch_mgba.sh`` can use it directly. Diagnostics and the durable receipt
path go to stderr. This helper never starts an emulator.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Sequence


RECEIPT_RELATIVE_ROOT = Path("tmp/headed-launch-receipts")
RECEIPT_SCHEMA = "penta-headed-launch-provenance-v1"
ROM_SUFFIXES = frozenset({".gb", ".gbc", ".gba", ".zip"})


class LaunchPreparationError(RuntimeError):
    """The launcher cannot safely resolve the explicitly selected ROM."""


@dataclass(frozen=True)
class PreparedLaunch:
    rom_path: Path
    rom_sha256: str
    receipt_path: Path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_extra_rom_arguments(arguments: Sequence[str]) -> None:
    for argument in arguments:
        if argument.startswith("-"):
            continue
        if Path(argument).suffix.lower() in ROM_SUFFIXES:
            raise LaunchPreparationError(
                "refusing extra ROM-like positional argument after the "
                f"selected ROM: {argument}"
            )


def resolve_selected_rom(project_root: Path, requested_rom: str | None) -> Path:
    if requested_rom is None:
        raise LaunchPreparationError(
            "no ROM was supplied; pass the intended ROM explicitly"
        )

    raw = Path(requested_rom)
    selected = raw if raw.is_absolute() else project_root / raw
    try:
        resolved = selected.resolve(strict=True)
    except OSError as error:
        raise LaunchPreparationError(
            f"selected ROM cannot be resolved: {selected}: {error}"
        ) from error
    if not resolved.is_file():
        raise LaunchPreparationError(f"selected ROM is not a file: {resolved}")
    return resolved


def write_receipt(
    project_root: Path,
    requested_rom: str | None,
    rom_path: Path,
    rom_sha256: str,
) -> Path:
    receipt_root = project_root / RECEIPT_RELATIVE_ROOT
    receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp_ns = time.time_ns()
    timestamp_utc = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    receipt_path = receipt_root / (
        f"{timestamp_ns}-{os.getpid()}-{rom_sha256[:12]}.json"
    )
    temporary_path = receipt_root / f".{receipt_path.name}.writing"
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "timestamp_utc": timestamp_utc,
        "timestamp_unix_ns": timestamp_ns,
        "project_root": str(project_root),
        "launcher": str(project_root / "scripts/launch_mgba.sh"),
        "rom": {
            "requested_path": requested_rom,
            "resolved_path": str(rom_path),
            "sha256": rom_sha256,
        },
    }
    encoded = (
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, receipt_path)
        directory_descriptor = os.open(receipt_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return receipt_path


def prepare_launch(
    project_root: Path,
    requested_rom: str | None,
    extra_arguments: Sequence[str] = (),
) -> PreparedLaunch:
    try:
        root = project_root.resolve(strict=True)
    except OSError as error:
        raise LaunchPreparationError(
            f"project root cannot be resolved: {project_root}: {error}"
        ) from error
    if not root.is_dir():
        raise LaunchPreparationError(f"project root is not a directory: {root}")

    reject_extra_rom_arguments(extra_arguments)
    rom_path = resolve_selected_rom(root, requested_rom)
    try:
        rom_sha256 = hash_file(rom_path)
    except OSError as error:
        raise LaunchPreparationError(
            f"cannot hash selected ROM {rom_path}: {error}"
        ) from error

    try:
        receipt_path = write_receipt(
            root, requested_rom, rom_path, rom_sha256
        )
    except OSError as error:
        raise LaunchPreparationError(
            f"cannot durably write headed-launch receipt: {error}"
        ) from error
    return PreparedLaunch(rom_path, rom_sha256, receipt_path)


def parse_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--rom")
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="one post-ROM emulator argument to screen for another ROM path",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(sys.argv[1:] if arguments is None else arguments)
    try:
        prepared = prepare_launch(
            options.project_root, options.rom, options.extra_arg
        )
    except LaunchPreparationError as error:
        print(f"headed-launch: BLOCKED: {error}", file=sys.stderr)
        return 65
    print(
        "headed-launch: verified "
        f"SHA-256 {prepared.rom_sha256}; receipt={prepared.receipt_path}",
        file=sys.stderr,
    )
    print(prepared.rom_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
