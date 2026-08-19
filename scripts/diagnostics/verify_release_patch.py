#!/usr/bin/env python3
"""Prove the distributable IPS reconstructs the exact release ROM."""

from __future__ import annotations

import argparse
import hashlib
from itertools import zip_longest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from penta_dragon_dx.patch_builder import apply_ips_patch, build_ips_patch


DEFAULT_BASE = ROOT / "rom" / "Penta Dragon (J).gb"
DEFAULT_ROM = ROOT / "rom" / "working" / "penta_dragon_dx_FIXED.gb"
DEFAULT_PATCH = ROOT / "rom" / "penta_dragon_dx.ips"
SUPPORTED_BASE_MD5 = "df43e0adfdc74b2829c7e95e91c71a28"


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--patch", type=Path, default=DEFAULT_PATCH)
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help=(
            "build the IPS in memory and prove its round trip without "
            "requiring or changing the checked-in release patch"
        ),
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help=(
            "atomically replace --patch with the deterministic patch for "
            "the selected ROM, then verify the checked-in form"
        ),
    )
    args = parser.parse_args()
    if args.candidate_only and args.update:
        parser.error("--candidate-only and --update are mutually exclusive")

    required = [
        ("base ROM", args.base),
        ("release ROM", args.rom),
    ]
    if not args.candidate_only and not args.update:
        required.append(("IPS patch", args.patch))
    for label, path in required:
        if not path.is_file():
            return fail(f"{label} not found: {path}")

    base = args.base.read_bytes()
    release = args.rom.read_bytes()
    base_hash = md5(base)
    release_hash = md5(release)

    if base_hash != SUPPORTED_BASE_MD5:
        return fail(
            f"unsupported base ROM MD5 {base_hash}; expected {SUPPORTED_BASE_MD5}"
        )
    if len(release) < len(base):
        return fail(f"release ROM shrank: {len(base)} -> {len(release)}")

    try:
        rebuilt_patch = build_ips_patch(base, release)
    except ValueError as exc:
        return fail(f"could not rebuild IPS: {exc}")
    if build_ips_patch(base, release) != rebuilt_patch:
        return fail("two in-memory IPS builds were not byte-identical")
    if args.candidate_only:
        patch = rebuilt_patch
        patch_hash = md5(patch)
    else:
        if args.update:
            args.patch.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.patch.with_suffix(args.patch.suffix + ".tmp")
            temporary.write_bytes(rebuilt_patch)
            temporary.replace(args.patch)
            print(
                f"UPDATED: deterministic IPS {args.patch} "
                f"({len(rebuilt_patch)} bytes/{md5(rebuilt_patch)})"
            )
        patch = args.patch.read_bytes()
        patch_hash = md5(patch)
        if patch != rebuilt_patch:
            return fail(
                "checked-in IPS is stale or nondeterministic: "
                f"actual {len(patch)} bytes/{patch_hash}, "
                f"expected {len(rebuilt_patch)} bytes/{md5(rebuilt_patch)}"
            )

    try:
        reconstructed = apply_ips_patch(base, patch)
    except ValueError as exc:
        return fail(f"IPS parser rejected the release patch: {exc}")
    if reconstructed != release:
        mismatches = sum(
            actual != expected
            for actual, expected in zip_longest(
                reconstructed, release, fillvalue=None
            )
        )
        return fail(
            f"IPS output differs from release ROM in {mismatches} byte(s): "
            f"{md5(reconstructed)} != {release_hash}"
        )

    if md5(args.base.read_bytes()) != base_hash:
        return fail("base ROM changed while verifying the IPS")
    if md5(args.rom.read_bytes()) != release_hash:
        return fail("release ROM changed while verifying the IPS")
    if (
        not args.candidate_only
        and md5(args.patch.read_bytes()) != patch_hash
    ):
        return fail("IPS changed while verifying itself")

    print(f"PASS: supported base ROM MD5 {base_hash}")
    print(f"PASS: ROM size {len(base)} -> {len(release)} bytes")
    mode = "in-memory candidate IPS" if args.candidate_only else "checked-in IPS"
    print(
        f"PASS: deterministic {mode} {len(patch)} bytes, MD5 {patch_hash}"
    )
    print(f"PASS: IPS reconstructs exact release ROM MD5 {release_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
