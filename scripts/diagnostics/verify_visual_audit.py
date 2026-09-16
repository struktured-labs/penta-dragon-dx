#!/usr/bin/env python3
"""Verify visual-audit coverage, media integrity, and human-review structure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs/audit/visual_audit_catalog.json"
SCHEMA = "penta-dragon-dx-visual-audit-v1"
FORBIDDEN_SUFFIXES = {".gb", ".gbc", ".gba", ".sav", ".ram", ".ss", ".ss0", ".ss1"}
SHA256_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<path>.+)$")
OWNERSHIP_MARKER = ".penta-visual-audit-owned"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    site = args.site.resolve()
    manifest_path = site / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        catalog = json.loads(CATALOG.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: unreadable audit input: {exc}")
        return 1

    failures: list[str] = []
    warnings: list[str] = []

    # CHECKSUMS is the portable whole-site integrity contract.  Verify its
    # inventory before trusting any embedded manifest claims, including the
    # HTML, JavaScript, CSS, and machine receipt itself.
    checksum_path = site / "CHECKSUMS.sha256"
    checksum_rows: dict[str, str] = {}
    if checksum_path.is_file():
        for line_number, raw in enumerate(checksum_path.read_text().splitlines(), 1):
            match = SHA256_LINE.fullmatch(raw)
            if not match:
                failures.append(f"malformed checksum line {line_number}")
                continue
            relative = Path(match.group("path"))
            name = relative.as_posix()
            if relative.is_absolute() or ".." in relative.parts:
                failures.append(f"unsafe checksum path {name}")
                continue
            if name in checksum_rows:
                failures.append(f"duplicate checksum path {name}")
                continue
            checksum_rows[name] = match.group("digest")
        actual_files = {
            path.relative_to(site).as_posix()
            for path in site.rglob("*")
            if path.is_file()
            and path.name not in {"CHECKSUMS.sha256", OWNERSHIP_MARKER}
        }
        if set(checksum_rows) != actual_files:
            absent = sorted(actual_files - set(checksum_rows))
            extra = sorted(set(checksum_rows) - actual_files)
            failures.append(
                f"checksum inventory mismatch: absent={absent}, extra={extra}"
            )
        for name, expected in checksum_rows.items():
            path = site / name
            if path.is_file() and digest(path) != expected:
                failures.append(f"whole-site checksum mismatch for {name}")
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                failures.append(f"forbidden generated artifact in site: {name}")
    if manifest.get("schema") != SCHEMA:
        failures.append(f"wrong schema: {manifest.get('schema')!r}")
    marker = site / OWNERSHIP_MARKER
    if not marker.is_file() or marker.read_text().strip() != SCHEMA:
        failures.append("site ownership/schema marker is missing or invalid")
    candidate = str(manifest.get("candidate", {}).get("sha256", ""))
    if len(candidate) != 64:
        failures.append("candidate SHA-256 is missing/invalid")
    if args.candidate_sha256 and candidate != args.candidate_sha256:
        failures.append("site candidate hash differs from requested hash")
    if manifest.get("catalog_sha256") != digest(CATALOG):
        failures.append("site was built from a different coverage catalog")

    expected_specs = {row["id"]: row for row in catalog["categories"]}
    intentional_catalog = {
        str(source): str(reason)
        for source, reason in catalog.get("intentional_blank_sources", {}).items()
    }
    categories = {row["id"]: row for row in manifest.get("categories", [])}
    if set(categories) != set(expected_specs):
        failures.append(
            "category inventory mismatch: "
            f"expected {sorted(expected_specs)}, saw {sorted(categories)}"
        )

    review_presets = manifest.get("review_presets", {})
    if review_presets != catalog.get("review_presets", {}):
        failures.append("review preset inventory differs from the canonical catalog")

    audit_ids: set[str] = set()
    referenced_media: dict[str, str] = {}
    calculated_expected = calculated_covered = 0
    calculated_failed_categories = 0
    calculated_suspicious: set[str] = set()
    calculated_intentional: dict[str, str] = {}
    for category_id, spec in expected_specs.items():
        category = categories.get(category_id)
        if not category:
            continue
        expected = int(spec["expected_items"])
        items = category.get("items", [])
        calculated_expected += expected
        if len(items) != expected:
            failures.append(f"{category_id}: expected {expected} items, saw {len(items)}")
        for row in items:
            audit_id = str(row.get("audit_id", ""))
            if not audit_id.startswith(category_id + ":"):
                failures.append(f"{category_id}: malformed audit id {audit_id!r}")
            if audit_id in audit_ids:
                failures.append(f"duplicate audit id: {audit_id}")
            audit_ids.add(audit_id)
            status = row.get("status")
            if status not in ("covered", "partial", "missing", "failed"):
                failures.append(f"{audit_id}: invalid status {status!r}")
            if status == "covered":
                calculated_covered += 1
            images = row.get("images", [])
            if status == "covered" and len(images) < int(row.get("minimum_images", 1)):
                failures.append(f"{audit_id}: covered without its minimum image count")
            for image in images:
                visually_blank = (
                    int(image.get("distinct_colors", 0)) < 2
                    or float(image.get("dominant_fraction", 1.0)) >= 0.9995
                )
                source = str(image.get("source", ""))
                if visually_blank:
                    if image.get("intentional_blank") is True:
                        reason = str(image.get("intentional_reason", ""))
                        if not reason or intentional_catalog.get(source) != reason:
                            failures.append(
                                f"{audit_id}: intentional blank lacks its catalog reason"
                            )
                        else:
                            calculated_intentional[source] = reason
                    else:
                        calculated_suspicious.add(source)
                relative = Path(str(image.get("media", "")))
                if relative.is_absolute() or ".." in relative.parts:
                    failures.append(f"{audit_id}: unsafe media path {relative}")
                    continue
                path = site / relative
                if not path.is_file():
                    failures.append(f"{audit_id}: missing media {relative}")
                    continue
                actual = digest(path)
                if actual != image.get("sha256"):
                    failures.append(f"{audit_id}: hash mismatch for {relative}")
                previous = referenced_media.setdefault(relative.as_posix(), actual)
                if previous != actual:
                    failures.append(f"{audit_id}: one media path names two hashes")
                if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                    failures.append(f"{audit_id}: forbidden artifact in site: {relative}")
        calculated_failed_categories += any(
            row.get("status") != "covered" for row in items
        )

    for preset_id, preset in review_presets.items():
        selected = [str(row.get("audit_id", "")) for row in preset.get("items", [])]
        if not selected:
            failures.append(f"review preset {preset_id}: no selected audit items")
        if len(selected) != len(set(selected)):
            failures.append(f"review preset {preset_id}: duplicate audit IDs")
        unknown = sorted(set(selected) - audit_ids)
        if unknown:
            failures.append(f"review preset {preset_id}: unknown audit IDs {unknown}")

    stage = categories.get("stages", {})
    for row in stage.get("items", []):
        og = [image for image in row["images"] if image.get("side") == "og"]
        dx = [image for image in row["images"] if image.get("side") == "dx"]
        pairs = {image.get("pair_key") for image in row["images"]}
        if len(og) != 20 or len(dx) != 20 or len(pairs) != 20:
            failures.append(
                f"{row['audit_id']}: expected 20 OG/DX pairs, saw "
                f"{len(og)} OG, {len(dx)} DX, {len(pairs)} pair keys"
            )
    for row in categories.get("bosses", {}).get("items", []):
        og = [image for image in row["images"] if image.get("side") == "og"]
        dx = [image for image in row["images"] if image.get("side") == "dx"]
        if len(og) != 4 or len(dx) != 4:
            failures.append(f"{row['audit_id']}: expected four OG + four DX phases")

    coverage = manifest.get("coverage", {})
    if coverage.get("expected_items") != calculated_expected:
        failures.append("top-level expected coverage count is inconsistent")
    if coverage.get("covered_items") != calculated_covered:
        failures.append("top-level covered count is inconsistent")
    missing = calculated_expected - calculated_covered
    if coverage.get("missing_items") != missing:
        failures.append("top-level missing count is inconsistent")
    if coverage.get("failed_categories") != calculated_failed_categories:
        failures.append("top-level failed-category count is inconsistent")
    expected_status = "complete" if not missing and not calculated_suspicious else "gaps"
    if manifest.get("status") != expected_status:
        failures.append(
            f"top-level status is inconsistent: expected {expected_status!r}"
        )
    if manifest.get("media", {}).get("unique_images") != len(referenced_media):
        failures.append(
            "unique media count differs from referenced content-addressed files "
            f"({manifest.get('media', {}).get('unique_images')} vs {len(referenced_media)})"
        )
    media_bytes = sum((site / relative).stat().st_size for relative in referenced_media)
    if manifest.get("media", {}).get("bytes") != media_bytes:
        failures.append("top-level unique media-byte count is inconsistent")
    suspicious = manifest.get("media", {}).get("suspicious_blank_images", [])
    if set(suspicious) != calculated_suspicious:
        failures.append("top-level suspicious blank inventory is inconsistent")
    intentional = {
        str(row.get("source", "")): str(row.get("reason", ""))
        for row in manifest.get("media", {}).get("intentional_blank_images", [])
    }
    if intentional != calculated_intentional:
        failures.append("top-level intentional blank inventory is inconsistent")
    if suspicious:
        warnings.append(f"{len(suspicious)} suspicious blank/dominant images")
    if args.strict and missing:
        failures.append(f"strict coverage requires zero gaps; {missing} items are incomplete")
    if args.strict and suspicious:
        failures.append("strict coverage rejects suspicious blank/dominant images")

    for required in ("index.html", "site.css", "site.js", "CHECKSUMS.sha256"):
        if not (site / required).is_file():
            failures.append(f"site asset missing: {required}")
    if (site / "index.html").is_file():
        page = (site / "index.html").read_text()
        for token in (
            "audit-data", "Export review", candidate,
            'href="manifest.json"', 'href="CHECKSUMS.sha256"',
            'id="queue-resume"', 'id="save-state"', "Keyboard review",
        ):
            if token not in page:
                failures.append(f"index.html lacks required token {token!r}")
    if (site / "site.js").is_file():
        script = (site / "site.js").read_text()
        for token in (
            'fetch("/api/review"',
            'navigator.sendBeacon?.("/api/review"',
            'g: () => mark("good", "next")',
            'i: () => mark("issue", "notes")',
            'j: () => move(1)',
            'k: () => move(-1)',
        ):
            if token not in script:
                failures.append(f"site.js lacks durable queue token {token!r}")

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        for warning in warnings:
            print("WARN: " + warning)
        return 1
    for warning in warnings:
        print("WARN: " + warning)
    print(
        f"PASS: {calculated_covered}/{calculated_expected} visual items, "
        f"{len(referenced_media)} hash-verified images, candidate {candidate[:12]}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
