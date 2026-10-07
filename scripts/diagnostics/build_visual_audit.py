#!/usr/bin/env python3
"""Build the hash-bound human + machine Penta Dragon DX visual audit site.

The builder consumes one deterministic-suite artifact directory. It never
launches an emulator and never guesses that a loose screenshot belongs to the
candidate. Every evidence family is admitted only through the suite matrix or
an explicit hash-bound supplemental receipt (currently miniboss/projectile).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable

from PIL import Image
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "docs/audit/visual_audit_catalog.json"
DEFAULT_PALETTE = ROOT / "palettes/penta_palettes_v097.yaml"
ASSET_ROOT = Path(__file__).with_name("visual_audit_assets")
SITE_SCHEMA = "penta-dragon-dx-visual-audit-v1"
OWNERSHIP_MARKER = ".penta-visual-audit-owned"


def exact_low_health_pair(receipt: dict, candidate_hash: str) -> bool:
    """#67: shifted/v1 or visual-only passes cannot qualify the current audit."""
    required = (
        "both low-health hazard replays pass",
        "full unshifted state trace and rendered corpus are byte-exact",
        "complete native audio video state and input timeline are byte-exact",
    )
    if (receipt.get("schema") != "penta-low-health-hazard-determinism-v2"
            or receipt.get("passed") is not True
            or receipt.get("rom_sha256") != candidate_hash
            or receipt.get("statuses") != [0, 0]
            or not all(receipt.get("checks", {}).get(key) is True for key in required)):
        return False
    exact = receipt.get("exact_comparison", {})
    counts = exact.get("row_counts", [])
    samples = receipt.get("samples", 0)
    if (exact.get("passed") is not True or not isinstance(samples, int) or samples <= 0
            or len(counts) != 2 or counts[0] != counts[1]
            or not isinstance(counts[0], int) or not samples <= counts[0] <= samples + 8
            or exact.get("compared_frames") != counts[0]
            or exact.get("row_mismatch_samples") != []
            or exact.get("image_mismatch_samples") != []
            or exact.get("extra_images") != [[], []]):
        return False
    replays = receipt.get("replays", [])
    if len(replays) != 2:
        return False
    for replay in replays:
        native = replay.get("native_capture", {})
        if (replay.get("passed") is not True or replay.get("rom_sha256") != candidate_hash
                or native.get("status") != "COMPLETE_CAPTURE_FILES"
                or native.get("restored_replay_epoch", {}).get("status") != "PASS"):
            return False
    for suffix in ("s16le", "video", "states", "timeline.tsv"):
        hashes = [replay["native_capture"].get("hashes", {}).get("native." + suffix)
                  for replay in replays]
        if (not isinstance(hashes[0], str) or not re.fullmatch(r"[0-9a-f]{64}", hashes[0])
                or hashes[0] != hashes[1]):
            return False
    return True


def observed_low_health_images(directory: Path) -> list[tuple[int, Path]]:
    """Select gallery illustrations by observed warning, not assumed timing.

    This does not filter acceptance: the admitted v2 pair already compared
    the entire corpus. Healthy recovery must not be captioned low-health.
    """
    with (directory / "low-health.frames.tsv").open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    selected = []
    for expected, row in enumerate(rows, 1):
        if int(row["sample"]) != expected:
            raise RuntimeError("missing or reordered low-health gallery sample")
        image = directory / f"low-health.frame{expected:04d}.png"
        if not image.is_file():
            raise RuntimeError("missing low-health gallery image")
        if row.get("health_phase") == "low" and row.get("dd06") == "01":
            selected.append((expected, image))
    if not selected:
        raise RuntimeError("no observed native warning for low-health gallery")
    return selected

BG_NAMES = ("Dungeon", "BG1", "BG2", "BG3", "BG4", "BG5", "BG6", "BG7")
OBJ_NAMES = (
    "EnemyProjectile", "SaraDragon", "SaraWitch", "SaraProjectileAndCrow",
    "Hornets", "OrcGround", "Humanoid", "Catfish",
)

MINIBOSS_NAMES = (
    "Gargoyle", "Spider", "Crimson", "Ice", "Void", "Poison", "Knight",
    "Angela", "Boss 9 (unnamed)", "Boss 10 (unnamed)",
    "Boss 11 (unnamed)", "Boss 12 (unnamed)", "Boss 13 (unnamed)",
    "Boss 14 (unnamed)", "Boss 15 (unnamed)",
    "Boss 16 (unfinished / unnamed)",
)

GATE_REQUIREMENTS = {
    "stages": ("stage_side_by_side_all7",),
    "bosses": ("boss_material_side_by_side", "boss_geometry_all9"),
    "pickups": ("pickup_live_palettes",),
    "heroes": ("spotlight_full_roster",),
    "monsters": ("spotlight_full_roster",),
    "opening": ("opening_cutscene",),
    "pre_final": ("pre_final_inventory",),
    "ending": ("ending_inventory_a", "ending_inventory_b"),
    "story_keyframes": ("story_attr_production",),
    "secret": ("bonus_stage_live",),
    "menus": ("menu_icon_palettes",),
    "hazards": (
        "stage1_current_hazard_state", "stage1_current_hazard_menu",
        "low_health_flicker",
    ),
    "title": ("title_showcase", "title_cursor"),
    "death": ("death_gameover",),
}


def digest(path: Path) -> str:
    block_hash = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            block_hash.update(block)
    return block_hash.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON evidence is not an object: {path}")
    return value


def bgr555_to_css(raw: str | int) -> str:
    value = int(str(raw), 16) if isinstance(raw, str) else raw
    channels = (value & 31, (value >> 5) & 31, (value >> 10) & 31)
    return "#" + "".join(f"{round(channel * 255 / 31):02x}" for channel in channels)


def nested(document: dict[str, Any], dotted: str) -> dict[str, Any]:
    value: Any = document
    for part in dotted.split("."):
        value = value[part]
    if not isinstance(value, dict) or "colors" not in value:
        raise KeyError(f"palette row lacks colors: {dotted}")
    return value


def palette_row(document: dict[str, Any], dotted: str) -> dict[str, Any]:
    row = nested(document, dotted)
    raw = [str(value).upper().removeprefix("0X") for value in row["colors"]]
    return {
        "source": dotted,
        "short_name": dotted.rsplit(".", 1)[-1],
        "bgr555": raw,
        "rgb": [bgr555_to_css(value) for value in raw],
        **({"slot": int(row["slot"])} if "slot" in row else {}),
    }


def item_evidence_digest(built: dict[str, Any]) -> str:
    """Hash exactly what a reviewer sees/uses to make one verdict."""
    payload = {
        "status": built.get("status"),
        "subtitle": built.get("subtitle", ""),
        "images": [
            {
                key: image.get(key)
                for key in ("sha256", "caption", "side", "pair_key")
                if image.get(key) is not None
            }
            for image in built.get("images", [])
        ],
        "palettes": built.get("palettes", []),
        "machine_notes": built.get("machine_notes", []),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def quality(path: Path) -> dict[str, int | float | list[int]]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        colors = image.getcolors(maxcolors=max(1_000_000, image.width * image.height)) or []
        total = image.width * image.height
    dominant = max((count for count, _ in colors), default=total)
    chromatic = sum(count for count, rgb in colors if max(rgb) - min(rgb) >= 20)
    return {
        "width": image.width,
        "height": image.height,
        "distinct_colors": len(colors),
        "dominant_fraction": round(dominant / total, 6),
        "chromatic_pixels": chromatic,
    }


def spread_best(paths: list[Path], count: int) -> list[Path]:
    """Pick the most informative frame from each deterministic time bucket."""
    paths = sorted(paths)
    if len(paths) <= count:
        return paths
    selected: list[Path] = []
    for index in range(count):
        start = index * len(paths) // count
        end = max(start + 1, (index + 1) * len(paths) // count)
        bucket = paths[start:end]
        selected.append(
            max(
                bucket,
                key=lambda path: (
                    int(quality(path)["chromatic_pixels"]),
                    int(quality(path)["distinct_colors"]),
                    -paths.index(path),
                ),
            )
        )
    return selected


class MediaStore:
    def __init__(self, output: Path, evidence_root: Path) -> None:
        self.output = output
        self.evidence_root = evidence_root
        self.records: dict[str, dict[str, Any]] = {}

    def source_name(self, path: Path) -> str:
        for base, prefix in ((self.evidence_root, "suite-artifacts"), (ROOT, "repo")):
            try:
                return f"{prefix}/{path.resolve().relative_to(base.resolve()).as_posix()}"
            except ValueError:
                continue
        return path.name

    def add(
        self,
        path: Path,
        *,
        caption: str,
        alt: str | None = None,
        side: str | None = None,
        pair_key: str | None = None,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        checksum = digest(path)
        if expected_sha256 and checksum != expected_sha256:
            raise RuntimeError(
                f"image hash mismatch for {path}: expected {expected_sha256}, got {checksum}"
            )
        metrics = quality(path)
        relative = Path("media") / checksum[:2] / f"{checksum}.png"
        destination = self.output / relative
        if checksum not in self.records:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            self.records[checksum] = {
                "sha256": checksum,
                "media": relative.as_posix(),
                "source": self.source_name(path),
                "size": destination.stat().st_size,
                **metrics,
            }
        return {
            **self.records[checksum],
            # Preserve the logical source per card even when two intentional
            # blank frames deduplicate to one content-addressed media file.
            "source": self.source_name(path),
            "caption": caption,
            "alt": alt or caption,
            **({"side": side} if side else {}),
            **({"pair_key": pair_key} if pair_key else {}),
        }


def item(
    category: str,
    item_id: str,
    label: str,
    images: list[dict[str, Any]],
    *,
    minimum: int = 1,
    subtitle: str = "",
    palettes: list[dict[str, Any]] | None = None,
    notes: list[str] | None = None,
    force_status: str | None = None,
) -> dict[str, Any]:
    status = force_status or ("covered" if len(images) >= minimum else "partial" if images else "missing")
    evidence_payload = {
        "status": status,
        "subtitle": subtitle,
        "images": [
            {
                key: image.get(key)
                for key in ("sha256", "caption", "side", "pair_key")
                if image.get(key) is not None
            }
            for image in images
        ],
        "palettes": palettes or [],
        "machine_notes": notes or [],
    }
    evidence_sha256 = hashlib.sha256(
        json.dumps(
            evidence_payload, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return {
        "audit_id": f"{category}:{item_id}",
        "id": item_id,
        "label": label,
        "subtitle": subtitle,
        "status": status,
        "minimum_images": minimum,
        "images": images,
        "palettes": palettes or [],
        "machine_notes": notes or [],
        # A human verdict is valid only for this exact visual/semantic packet.
        # This intentionally excludes absolute source paths while including
        # rendered pixels, pair roles, captions, palettes, and machine notes.
        "evidence_sha256": evidence_sha256,
    }


def resolve_image(directory: Path, raw: str) -> Path:
    candidate = Path(raw)
    choices = [candidate, directory / candidate, directory / candidate.name]
    for choice in choices:
        if choice.is_file():
            return choice
    return directory / candidate.name


def matrix_context(evidence_root: Path, release_receipt: Path) -> tuple[dict[str, Any], dict[str, str], str]:
    matrix_path = evidence_root.parent / "manifest.json"
    matrix = read_json(matrix_path)
    receipt = read_json(release_receipt)
    candidate_hash = str(receipt.get("candidate", {}).get("sha256", ""))
    if len(candidate_hash) != 64 or receipt.get("status") != "passed":
        raise RuntimeError("release receipt is not a passing candidate receipt")
    results = {str(row.get("name")): str(row.get("status")) for row in matrix.get("results", [])}
    if not results or matrix.get("status") != "emulator-pass":
        raise RuntimeError("suite matrix is not a complete emulator pass")
    tested = {str(value) for value in matrix.get("tested_rom_sha256", [])}
    if tested:
        if candidate_hash not in tested:
            raise RuntimeError("suite matrix tested a different ROM hash")
    else:
        # Older native full-matrix manifests preserve exact source/tested ROM
        # paths and an end-of-run integrity flag but predate the explicit SHA
        # array. Bind those bytes directly; never infer identity from MD5 or a
        # plausible filename.
        source_rom = Path(str(matrix.get("source_rom", "")))
        tested_rom = Path(str(matrix.get("tested_rom", "")))
        if (
            not source_rom.is_file()
            or not tested_rom.is_file()
            or digest(source_rom) != candidate_hash
            or digest(tested_rom) != candidate_hash
            or matrix.get("rom_hashes_intact") is not True
        ):
            raise RuntimeError(
                "legacy suite matrix source/tested ROM bytes are not bound "
                "to the release candidate"
            )
    return matrix, results, candidate_hash


def gate_ok(results: dict[str, str], category: str) -> tuple[bool, list[str]]:
    required = GATE_REQUIREMENTS.get(category, ())
    missing = [name for name in required if results.get(name) != "passed"]
    return not missing, missing


def build_stages(store: MediaStore, root: Path, candidate_hash: str) -> list[dict[str, Any]]:
    directory = root / "stage-side-by-side"
    manifest = read_json(directory / "manifest.json")
    if manifest.get("status") != "pass" or manifest.get("dx_rom_sha256") != candidate_hash:
        raise RuntimeError("stage side-by-side evidence is not bound to the candidate")
    items = []
    for number in range(1, 8):
        images = []
        for side in ("og", "dx"):
            paths = sorted((directory / f"stage{number}" / side).glob("run.f*.png"))
            for path in paths:
                frame = int(path.stem.rsplit("f", 1)[-1])
                images.append(store.add(
                    path,
                    caption=f"Stage {number} · {side.upper()} · frame {frame}",
                    side=side,
                    pair_key=f"frame {frame:04d}",
                ))
        og_count = sum(image.get("side") == "og" for image in images)
        dx_count = sum(image.get("side") == "dx" for image in images)
        notes = [f"{og_count} OG + {dx_count} DX scripted patrol samples; same input schedule."]
        items.append(item("stages", f"stage-{number}", f"Stage {number}", images,
                          minimum=40, subtitle=f"{og_count} OG / {dx_count} DX", notes=notes))
    return items


def build_bosses(
    store: MediaStore, root: Path, candidate_hash: str,
    catalog: dict[str, Any], palettes: dict[str, Any],
) -> list[dict[str, Any]]:
    directory = root / "boss-material-side-by-side"
    report = read_json(directory / "report.json")
    if report.get("status") != "pass" or int(report.get("boss_count", 0)) != 9:
        raise RuntimeError("boss comparison report is not a nine-boss pass")
    spec = {row["id"]: row for row in catalog["bosses"]}
    items = []
    for boss in report["bosses"]:
        boss_id = str(boss["boss"])
        images = []
        for record in boss["images"]:
            side = str(record["side"])
            source_dir = root / ("boss-og-material-gallery" if side == "og" else "boss-material-gallery")
            source = resolve_image(source_dir, str(record["path"]))
            frame = int(record["frame"])
            images.append(store.add(
                source,
                caption=f"{spec[boss_id]['label']} · {side.upper()} · frame {frame}",
                side=side,
                pair_key=f"phase {frame:03d}",
                expected_sha256=str(record["sha256"]),
            ))
        rows = [palette_row(palettes, dotted) for dotted in spec[boss_id]["palette_rows"]]
        items.append(item(
            "bosses", boss_id, spec[boss_id]["label"], images, minimum=8,
            subtitle=f"Scene {boss['scene']} · expected {boss['expected_material']}",
            palettes=rows,
            notes=["Four equal-duration OG/DX phase pairs; geometry and silhouette gates passed."],
        ))
    return items


def build_minibosses(
    store: MediaStore, receipt_path: Path | None, candidate_hash: str,
) -> list[dict[str, Any]]:
    receipt: dict[str, Any] = {}
    entries: dict[int, dict[str, Any]] = {}
    receipt_ok = False
    if receipt_path and receipt_path.is_file():
        receipt = read_json(receipt_path)
        receipt_ok = (
            receipt.get("rom_sha256") == candidate_hash
            and receipt.get("captured") == 16
            and receipt.get("deterministic_replay_exact") is True
            and receipt.get("status") in ("ok", "ok_with_palette_gaps")
        )
        entries = {int(row["ffbf"]): row for row in receipt.get("entries", [])}
    items = []
    for index, name in enumerate(MINIBOSS_NAMES, 1):
        row = entries.get(index)
        images = []
        rows: list[dict[str, Any]] = []
        notes: list[str] = []
        status = "missing"
        if row and receipt_path:
            source = resolve_image(receipt_path.parent, str(row["screenshot"]))
            images = [store.add(
                source,
                caption=f"FFBF {index:02d} · {name}",
                expected_sha256=str(row.get("screenshot_sha256") or "") or None,
            )]
            if row.get("expected_palette"):
                expected = row["expected_palette"]
                raw = [str(value) for value in expected["colors_bgr555"]]
                rows = [{
                    "source": f"boss_palettes.{expected['yaml_key']}",
                    "short_name": expected["yaml_key"],
                    "slot": expected["slot"],
                    "bgr555": raw,
                    "rgb": list(expected["colors_rgb888"]),
                }]
                if expected.get("aliased"):
                    notes.append(
                        f"ROM selector {index} aliases YAML palette source "
                        f"{int(expected['source_selector'])}; runtime OAM "
                        f"proved OBJ{int(expected['slot'])}."
                    )
            else:
                notes.append(
                    "No YAML palette is defined for this native index; the "
                    "capture is valid, but the production eight-row palette "
                    "table does not yet cover it."
                )
            context = row.get("native_context") or {}
            if context:
                notes.append(
                    f"Native Level {context.get('level')} section "
                    f"{context.get('section')} descriptor "
                    f"{context.get('descriptor')} was transplanted intact."
                )
            status = "covered" if receipt_ok else "partial"
        else:
            notes.append("Full deterministic 16-index miniboss receipt is missing.")
        items.append(item(
            "minibosses", f"ffbf-{index:02d}", name, images,
            subtitle=(
                f"FFBF={index} · "
                + (
                    f"YAML alias {int(row['expected_palette']['source_selector']):02d}"
                    if row and row.get("expected_palette", {}).get("aliased")
                    else "defined palette" if rows else "palette gap"
                )
            ),
            palettes=rows, notes=notes, force_status=status,
        ))
    return items


def build_pickups(
    store: MediaStore, root: Path, candidate_hash: str, palettes: dict[str, Any],
    receipt_path: Path | None = None,
) -> list[dict[str, Any]]:
    directory = (
        receipt_path.parent if receipt_path is not None
        else root / "pickup-live-palettes"
    )
    receipt_source = receipt_path or directory / "receipt.json"
    receipt = read_json(receipt_source)
    checks = receipt.get("checks", {})
    if (
        receipt.get("status") != "pass"
        or receipt.get("rom_sha256") != candidate_hash
        or len(receipt.get("pickups", [])) != 19
        or not isinstance(checks, dict)
        or not checks
        or not all(value is True for value in checks.values())
    ):
        raise RuntimeError("pickup receipt is not bound to the candidate")
    states = {str(row["state"]): row for row in receipt["states"]}
    items = []
    for pickup in receipt["pickups"]:
        state = states[str(pickup["state"])]
        source = resolve_image(directory, str(state["screenshot"]))
        expected_image_hash = state.get("screenshot_sha256")
        if expected_image_hash and digest(source) != expected_image_hash:
            raise RuntimeError(
                f"pickup screenshot hash mismatch for {pickup['name']}: {source}"
            )
        slot = int(pickup["palette"])
        images = [store.add(source, caption=f"{pickup['name']} · BG{slot} · {state['state']}")]
        items.append(item(
            "pickups", str(pickup["name"]).lower().replace(" ", "-"),
            str(pickup["name"]), images,
            subtitle=f"semantic BG slot {slot} · {pickup['matched']}/{pickup['found']} cells",
            palettes=[palette_row(palettes, f"bg_palettes.{BG_NAMES[slot]}")],
            notes=[
                "Screenshot may contain multiple pickups; the machine receipt identifies this form's exact tile cells.",
                "Evidence source: " + (
                    "candidate-bound supplemental recapture"
                    if receipt_path is not None else "deterministic suite matrix"
                ) + ".",
            ],
        ))
    return items


def build_spotlight(
    store: MediaStore, root: Path, candidate_hash: str, palettes: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    directory = root / "spotlight-full-roster"
    receipt = read_json(directory / "receipt.json")
    if receipt.get("status") != "ok" or receipt.get("captured") != 38:
        raise RuntimeError("spotlight receipt is not a full pass")
    # Older versions of this receipt use `rom` as a path; the matrix binding
    # supplies the candidate hash, and every image carries its own digest.
    actors = sorted(receipt["actors"], key=lambda row: int(row["identity"]))
    heroes, monsters = [], []
    for actor in actors:
        identity = int(actor["identity"])
        slot = int(actor["expected_palette_slot"])
        source = resolve_image(directory, str(actor["screenshot"]))
        actor_image = store.add(
            source,
            caption=(
                f"Spotlight ID {identity:02d} · centered actor · "
                f"resource {int(actor['resource_id']):02X} · OBJ{slot}"
            ),
            expected_sha256=str(actor["screenshot_sha256"]),
        )
        images = [actor_image]
        if actor.get("label_screenshot") and actor.get("label_screenshot_sha256"):
            label_source = resolve_image(directory, str(actor["label_screenshot"]))
            images.append(store.add(
                label_source,
                caption=f"Spotlight ID {identity:02d} · native name label",
                expected_sha256=str(actor["label_screenshot_sha256"]),
            ))
        row = palette_row(palettes, f"obj_palettes.{OBJ_NAMES[slot]}")
        target = heroes if identity < 2 else monsters
        category = "heroes" if identity < 2 else "monsters"
        label = ("Sara W" if identity == 0 else "Sara D") if identity < 2 else f"Spotlight actor {identity:02d}"
        name_pixels = int(actor.get("name_glyph_pixels", -1))
        if name_pixels > 0:
            notes = [
                "Two deterministic replays matched rendered PNG, hardware OAM, "
                f"and {name_pixels} visible in-game name-glyph pixels."
            ]
        elif identity == 37 and name_pixels == 0:
            notes = [
                "Two deterministic replays matched rendered PNG and hardware OAM. "
                "Native spotlight identity 37 publishes zero name-glyph pixels; "
                "the blank label is recorded evidence, not a missing capture."
            ]
        else:
            raise RuntimeError(
                f"spotlight identity {identity:02d} unexpectedly has no visible name glyphs"
            )
        if actor.get("stock_presentation"):
            notes.append("Stock presentation: " + str(actor["stock_presentation"]))
        target.append(item(
            category, f"identity-{identity:02d}", label,
            images,
            subtitle=f"resource {int(actor['resource_id']):02X} · OBJ{slot}",
            palettes=[row],
            notes=notes,
        ))
    return heroes, monsters


def build_projectiles(
    store: MediaStore, root: Path, receipt_path: Path | None,
    candidate_hash: str, catalog: dict[str, Any], palettes: dict[str, Any],
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    receipt_ok = False
    if receipt_path and receipt_path.is_file():
        receipt = read_json(receipt_path)
        receipt_ok = (
            receipt.get("status") == "pass"
            and receipt.get("rom_sha256") == candidate_hash
            and receipt.get("deterministic_replay_exact") is True
        )
        records = {str(row["id"]): row for row in receipt.get("projectiles", [])}
    context_dir = root / "gameplay-obj-palettes"
    context_paths = sorted(context_dir.glob("*.png"))
    items = []
    for spec in catalog["projectiles"]:
        record = records.get(spec["id"])
        images = []
        notes = []
        status = "missing"
        if record and receipt_path:
            for index, raw in enumerate(record.get("screenshots", []), 1):
                source = resolve_image(receipt_path.parent, str(raw["path"]))
                role = str(raw.get("role") or f"sample {index}")
                images.append(store.add(
                    source,
                    caption=f"{spec['label']} · {role}",
                    expected_sha256=str(raw.get("sha256") or "") or None,
                ))
            notes.append(
                f"Observed target tiles: {record.get('observed_tiles', [])}; "
                f"hardware slots: {record.get('palette_slots', [])}."
            )
            status = "covered" if receipt_ok and images else "partial"
        else:
            # Context is deliberately not counted as projectile proof. It is
            # useful to the human reviewer while keeping the machine gap red.
            hints = {
                "sara_w": ("sara_w",), "sara_d": ("sara_d",),
                "enemy": ("crow", "hornet", "orc"), "spider": ("spider",),
                "effects": ("hornet", "soldier"), "spiral": ("spiral",),
                "shield": ("shield",), "turbo": ("turbo",),
            }[spec["id"]]
            source = next((p for p in context_paths if any(hint in p.name.lower() for hint in hints)), None)
            if source:
                images.append(store.add(source, caption=f"Context only · {spec['label']} (not machine proof)"))
                status = "partial"
            notes.append("No deterministic OAM-targeted projectile receipt; context image does not close this gap.")
        items.append(item(
            "projectiles", spec["id"], spec["label"], images,
            palettes=[palette_row(palettes, spec["palette_row"])],
            notes=notes, force_status=status,
        ))
    return items


def panel_items(
    store: MediaStore, root: Path, directory_name: str, category: str,
    prefix: str, expected: int, candidate_hash: str,
) -> list[dict[str, Any]]:
    directory = root / directory_name
    manifest = read_json(directory / "manifest.json")
    if manifest.get("status") != "pass" or manifest.get("rom_sha256") != candidate_hash:
        raise RuntimeError(f"{category} manifest is not bound to the candidate")
    rows = list(manifest.get("panels", []))
    items = []
    for index in range(expected):
        images: list[dict[str, Any]] = []
        notes: list[str] = []
        if index < len(rows):
            row = rows[index]
            raw = row.get("screenshot") or row.get("image")
            if raw:
                source = resolve_image(directory, str(raw))
                images = [store.add(
                    source,
                    caption=f"{prefix} {index + 1:02d} · frame {row.get('frame')} · scene {int(row.get('scene', 0)):02X}",
                )]
            if int(row.get("unsafe_attr_cells", 0)):
                notes.append(f"Unsafe attribute cells: {row['unsafe_attr_cells']}")
        else:
            notes.append("Expected panel absent from the capture manifest.")
        items.append(item(
            category, f"panel-{index + 1:02d}", f"{prefix} {index + 1:02d}", images,
            subtitle=(f"frame {rows[index].get('frame')}" if index < len(rows) else "missing"),
            notes=notes,
        ))
    return items


def build_story_keyframes(
    store: MediaStore, root: Path, candidate_hash: str, palettes: dict[str, Any],
) -> list[dict[str, Any]]:
    directory = root / "story-attr-production"
    receipt = read_json(directory / "receipt.json")
    if receipt.get("status") != "passed" or receipt.get("rom_sha256") != candidate_hash:
        raise RuntimeError("story keyframe receipt is not bound to the candidate")
    items = []
    for row in receipt["results"]:
        source = resolve_image(directory, str(row["screenshot"]))
        palette_ids = sorted(int(key) for key in row.get("report", {}).get("palette_histogram", {}))
        palette_ids = palette_ids or sorted(int(key) for key in row.get("expected_art_histogram", {}))
        palette_rows = [palette_row(palettes, f"bg_palettes.{BG_NAMES[index]}") for index in palette_ids if 0 <= index < 8]
        state = str(row["state"])
        items.append(item(
            "story_keyframes", state.replace("_", "-"), state.replace("_", " ").title(),
            [store.add(source, caption=f"Story keyframe · {state} · {row['kind']}")],
            subtitle=f"{row['kind']} · art/palette {row['art_id_or_palette']}", palettes=palette_rows,
        ))
    return items


def generic_images(
    store: MediaStore, root: Path, category: str,
    sources: list[tuple[str, int]], expected: int,
) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for directory_name, count in sources:
        directory = root / directory_name
        directories = [directory] if directory.is_dir() else sorted(
            path for path in root.rglob(directory_name) if path.is_dir()
        )
        candidates = [
            path for candidate_dir in directories
            for path in candidate_dir.glob("*.png")
            if "contact-sheet" not in path.name
        ]
        paths.extend(spread_best(sorted(candidates), count))
    paths = paths[:expected]
    items = []
    for index in range(expected):
        if index < len(paths):
            source = paths[index]
            images = [store.add(source, caption=f"{category.replace('_', ' ').title()} · {source.stem}")]
            notes = []
        else:
            images = []
            notes = ["Expected deterministic sample is missing."]
        items.append(item(
            category, f"sample-{index + 1:02d}", f"Sample {index + 1:02d}", images,
            subtitle=(paths[index].stem if index < len(paths) else "missing"), notes=notes,
        ))
    return items


def build_title(
    store: MediaStore, root: Path, candidate_hash: str,
) -> list[dict[str, Any]]:
    """Build the full title audit from dedicated and traversal captures."""
    cursor = read_json(root / "title-cursor/receipt.json")
    stage_manifest = read_json(root / "stage-side-by-side/manifest.json")
    if (
        cursor.get("status") != "passed"
        or cursor.get("rom_sha256") != candidate_hash
        or stage_manifest.get("status") != "pass"
        or stage_manifest.get("dx_rom_sha256") != candidate_hash
    ):
        raise RuntimeError("title evidence is not bound to the candidate")
    report = dict(
        line.split("=", 1)
        for line in (root / "title-showcase/title.report").read_text().splitlines()
        if "=" in line
    )
    if report.get("status") != "ok" or int(report.get("screenshots", 0)) != 9:
        raise RuntimeError("title showcase report is incomplete")

    paths = sorted((root / "title-showcase").glob("*.png"))
    paths.extend(sorted((root / "title-cursor").glob("*.png")))
    paths.extend(
        root / f"stage-side-by-side/stage{stage}/dx/run.title.png"
        for stage in range(1, 5)
    )
    if len(paths) != 16 or not all(path.is_file() for path in paths):
        raise RuntimeError(f"title evidence produced {len(paths)} frames, expected 16")
    return [
        item(
            "title", f"sample-{index:02d}", f"Title sample {index:02d}",
            [store.add(source, caption=f"Title · {source.stem}")],
            subtitle=source.stem,
            notes=[
                "Candidate-bound title capture from the dedicated title checks "
                "or an independently replayed DX stage traversal."
            ],
        )
        for index, source in enumerate(paths, 1)
    ]


def build_current_hazards(
    store: MediaStore, root: Path, candidate_hash: str,
) -> list[dict[str, Any]]:
    """Publish the current candidate-bound Stage-1 hazard evidence."""
    directory = root / "stage1-current-hazard-menu"
    receipt = read_json(directory / "receipt.json")
    checks = receipt.get("checks", {})
    if (
        not receipt.get("passed")
        or receipt.get("rom_sha256") != candidate_hash
        or not checks.get("both replays retain full stationary hazard coverage")
        or not checks.get("replays are byte-deterministic")
    ):
        raise RuntimeError(
            "current Stage-1 hazard/menu receipt is not clean and candidate-bound"
        )
    replay = receipt.get("replays", [{}])[0]
    close_frame = int(replay.get("effective_menu_close_frame", 424))
    low_frame = int(replay.get("effective_low_health_frame", 454))
    frame_rows: list[tuple[int, Path]] = []
    for path in sorted((directory / "replay-1").glob("current-hazard-menu-frame*.png")):
        match = re.search(r"frame(\d+)$", path.stem)
        if match:
            frame_rows.append((int(match.group(1)), path))

    def select(first: int, last: int, count: int = 8) -> tuple[list[Path], dict[Path, int]]:
        rows = [(frame, path) for frame, path in frame_rows if first <= frame <= last]
        lookup = {path: frame for frame, path in rows}
        paths = spread_best([path for _, path in rows], count)
        return paths, lookup

    live_paths, live_lookup = select(120, 180)
    recovery_paths, recovery_lookup = select(close_frame + 5, max(close_frame + 5, low_frame - 1))

    low_directory = root / "low-health-flicker"
    low_outer = read_json(low_directory / "receipt.json")
    if not exact_low_health_pair(low_outer, candidate_hash):
        raise RuntimeError(
            "low-health deterministic wrapper is not clean and candidate-bound"
        )
    low_directory = low_directory / "replay-1"
    low = read_json(low_directory / "receipt.json")
    if not low.get("passed") or low.get("rom_sha256") != candidate_hash:
        raise RuntimeError("low-health flicker receipt is not bound to the candidate")
    low_rows = observed_low_health_images(low_directory)
    low_first = low_rows[0][0]
    low_lookup = {path: frame for frame, path in low_rows}
    low_paths = spread_best([path for _, path in low_rows], 8)

    groups = (
        (
            "Live rotating spike", live_paths, live_lookup,
            "Exact candidate-bound Stage-1 frames before opening the item menu; "
            "the hazard phase and rendered palette checks pass across both replays.",
        ),
        (
            "Post-menu hazard recovery", recovery_paths, recovery_lookup,
            "Stationary frames after the native item menu closes and before the "
            "low-health injection; hazard tiles and attributes remain atomic.",
        ),
        (
            "Low-health gameplay", low_paths, low_lookup,
            f"Observed native low-health warning from sample {low_first}; the "
            "rendered corpus is byte-exact across both replays.",
        ),
    )
    items: list[dict[str, Any]] = []
    item_index = 0
    for label, paths, lookup, note in groups:
        if len(paths) != 8:
            raise RuntimeError(
                f"hazard evidence {label} produced {len(paths)} frames, expected 8"
            )
        for index, source in enumerate(paths, 1):
            item_index += 1
            frame = lookup[source]
            items.append(item(
                "hazards", f"sample-{item_index:02d}", f"{label} {index:02d}",
                [store.add(source, caption=f"{label} · frame {frame}")],
                subtitle=f"verified frame {frame}", notes=[note],
            ))
    return items


def build_hazards(
    store: MediaStore, root: Path, candidate_hash: str,
) -> list[dict[str, Any]]:
    """Publish only human-readable frames from the hazard machine receipts.

    The spike verifier also owns a pre-settle frame and a deliberately forced
    miniboss fixture. Those are useful to the machine checks, but the forced
    flag produces a torn actor while the stock engine assembles its sprites.
    They must never be presented as screenshots of natural gameplay.
    """
    current_receipt = root / "stage1-current-hazard-menu/receipt.json"
    if current_receipt.is_file():
        return build_current_hazards(store, root, candidate_hash)

    spike_path = root / "stage1-spike-palettes.json"
    spike = read_json(spike_path)
    spike_rom = Path(str(spike.get("rom", "")))
    if (
        not spike.get("passed")
        or not spike_rom.is_file()
        or digest(spike_rom) != candidate_hash
    ):
        raise RuntimeError("Stage-1 spike receipt is not bound to the candidate")

    natural = spike.get("natural_live", {})
    floor_scroll = spike.get("floor_scroll", {})
    if not natural.get("passed") or not floor_scroll.get("passed"):
        raise RuntimeError("natural spike/miniboss hazard receipts did not pass")

    def receipt_frames(
        receipt: dict[str, Any], *, first: int, last: int | None = None,
    ) -> list[tuple[int, Path]]:
        rows: list[tuple[int, Path]] = []
        for row in receipt.get("periodic_pixel_receipts", []):
            frame = int(row.get("frame", -1))
            if frame < first or (last is not None and frame > last):
                continue
            path = resolve_image(spike_path.parent, str(row.get("path", "")))
            if path.is_file():
                rows.append((frame, path))
        return sorted(rows)

    # Frame 120 is the verifier's public pixel-settle boundary. Earlier
    # captures can still show the deliberately neutral boot phase.
    stable_rows = receipt_frames(natural, first=120)
    stable_lookup = {path: frame for frame, path in stable_rows}
    stable_paths = spread_best([path for _, path in stable_rows], 8)

    # The floor-scroll route reaches the miniboss naturally. Keep a bounded
    # before/after window instead of publishing the synthetic FFBF fixture.
    miniboss_frame = int(floor_scroll.get("miniboss_first_frame", -1))
    if miniboss_frame < 0:
        raise RuntimeError("natural floor-scroll receipt never reached miniboss")
    transition_rows = receipt_frames(
        floor_scroll,
        first=max(120, miniboss_frame - 90),
        last=miniboss_frame + 105,
    )
    transition_lookup = {path: frame for frame, path in transition_rows}
    transition_paths = spread_best([path for _, path in transition_rows], 8)

    low_directory = root / "low-health-flicker"
    low_outer = read_json(low_directory / "receipt.json")
    if not exact_low_health_pair(low_outer, candidate_hash):
        raise RuntimeError("low-health deterministic wrapper is not clean and candidate-bound")
    low_directory = low_directory / "replay-1"
    low = read_json(low_directory / "receipt.json")
    if (
        not low.get("passed")
        or str(low.get("rom_sha256", "")) != candidate_hash
    ):
        raise RuntimeError("low-health flicker receipt is not bound to the candidate")
    low_rows = observed_low_health_images(low_directory)
    low_first = low_rows[0][0]
    low_lookup = {path: frame for frame, path in low_rows}
    low_paths = spread_best([path for _, path in low_rows], 8)

    menu_directory = root / "stage1-hazard-menu"
    menu = read_json(menu_directory / "receipt.json")
    if (
        not menu.get("passed")
        or menu.get("rom_sha256") != candidate_hash
        or not menu.get("checks", {}).get(
            "all floor/ceiling menu round trips are byte-deterministic"
        )
    ):
        raise RuntimeError(
            "Stage-1 menu round-trip receipt is not clean and candidate-bound"
        )
    menu_rows: list[tuple[int, Path]] = []
    for prefix in ("floor-room12", "ceiling-room02"):
        _, case = next(
            (name, value)
            for name, value in menu["cases"].items()
            if name.startswith(prefix)
        )
        report = Path(case["raw_reports"][0])
        report_values = dict(
            line.split("=", 1)
            for line in report.read_text().splitlines()
            if "=" in line
        )
        rows: list[tuple[int, Path]] = []
        for entry in filter(
            None, report_values.get("periodic_render_trace", "").split(";")
        ):
            match = re.match(
                r"f(\d+):[0-9A-F]{2}:[0-9A-F]{2}:"
                r"[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}:(.*)",
                entry,
            )
            if match and int(match.group(1)) >= int(case["close_frame"]) + 5:
                path = Path(match.group(2))
                if path.is_file():
                    rows.append((int(match.group(1)), path))
        lookup = {path: frame for frame, path in rows}
        menu_rows.extend(
            (lookup[path], path)
            for path in spread_best([path for _, path in rows], 4)
        )
    menu_lookup = {path: frame for frame, path in menu_rows}
    menu_paths = [path for _, path in menu_rows]

    groups = (
        (
            "stable-spike", "Stable rotating spike", stable_paths,
            stable_lookup,
            "Natural room $12 capture after the frame-120 settle boundary; "
            "the synthetic miniboss fixture is excluded.",
        ),
        (
            "natural-miniboss", "Natural miniboss transition", transition_paths,
            transition_lookup,
            f"Natural Stage-1 traversal around miniboss frame {miniboss_frame}; "
            "no scene or miniboss flag was forced.",
        ),
        (
            "low-health", "Low-health gameplay", low_paths, low_lookup,
            f"Observed native low-health warning from sample {low_first}; "
            "the flicker gate passed across the full measured run.",
        ),
        (
            "post-menu", "Stationary post-menu hazards", menu_paths,
            menu_lookup,
            "Four floor-cylinder and four ceiling-cylinder frames after "
            "SELECT closes the item menu; no movement is permitted.",
        ),
    )
    items: list[dict[str, Any]] = []
    item_index = 0
    for prefix, label, paths, lookup, note in groups:
        if len(paths) != 8:
            raise RuntimeError(
                f"hazard evidence {prefix} produced {len(paths)} frames, expected 8"
            )
        for index, source in enumerate(paths, 1):
            item_index += 1
            frame = lookup[source]
            items.append(item(
                "hazards", f"sample-{item_index:02d}", f"{label} {index:02d}",
                [store.add(source, caption=f"{label} · frame {frame}")],
                subtitle=f"natural frame {frame}", notes=[note],
            ))
    return items


def build_secret(store: MediaStore, root: Path, candidate_hash: str) -> list[dict[str, Any]]:
    directory = root / "bonus-stage-live"
    receipt = read_json(directory / "receipt.json")
    if receipt.get("status") != "pass" or receipt.get("rom_sha256") != candidate_hash:
        raise RuntimeError("secret-stage receipt is not bound to the candidate")
    items = []
    for index, row in enumerate(receipt["screenshots"], 1):
        source = resolve_image(directory, str(row["path"]))
        items.append(item(
            "secret", f"phase-{index}", f"Secret jet phase {index}",
            [store.add(source, caption=f"Secret jet route · phase {index}", expected_sha256=str(row["sha256"]))],
            subtitle=f"{row['chromatic_pixels']} chromatic pixels",
        ))
    return items


def prepare_output(output: Path) -> None:
    output = output.resolve()
    allowed = (ROOT / "tmp").resolve()
    large = Path("/mnt/data/tmp").resolve()
    if not (output.is_relative_to(allowed) or output.is_relative_to(large)):
        raise RuntimeError("visual audit output must live under repo tmp/ or /mnt/data/tmp/")
    if output.exists():
        marker = output / OWNERSHIP_MARKER
        if not marker.is_file() or marker.read_text().strip() != SITE_SCHEMA:
            raise RuntimeError(f"refusing to replace unowned output directory: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / OWNERSHIP_MARKER).write_text(SITE_SCHEMA + "\n")


def render_html(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(str(manifest["title"]))
    candidate = html.escape(str(manifest["candidate"]["sha256"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="site.css"></head>
<body class="queue-mode"><header class="masthead"><div class="eyebrow">Penta Dragon DX · human + machine visual verification</div>
<h1>{title}</h1><p class="lede">A resumable, one-item-at-a-time review queue for palette containment, missing color, stray tiles, flicker clues, material seams, and OG/DX comparison. Verdicts are checkpointed both in this browser and by the local review server.</p>
<p class="hash">candidate {candidate} · <a href="manifest.json">machine manifest</a> · <a href="CHECKSUMS.sha256">whole-site checksums</a></p><div class="summary" id="summary"></div></header>
<div class="toolbar"><input id="search" type="search" placeholder="Search actors, stages, bosses, notes…">
<select id="category-filter"></select><select id="machine-filter"><option value="all">All machine states</option><option value="gaps">Machine gaps only</option><option value="covered">Covered only</option><option value="partial">Partial only</option><option value="missing">Missing only</option></select>
<select id="human-filter"><option value="all">All human states</option><option value="unreviewed">Unreviewed</option><option value="good">Looks good</option><option value="issue">Visual issue</option><option value="recapture">Needs recapture</option><option value="intentional">Intentional</option></select>
<select id="side-filter"><option value="both">OG + DX</option><option value="dx">DX only</option><option value="og">OG only</option></select>
<button id="export-review">Export review</button><label><button type="button" onclick="this.parentElement.querySelector('input').click()">Import review</button><input id="import-review" type="file" accept="application/json" hidden></label></div>
<div class="queuebar"><button id="queue-toggle" aria-pressed="true">Show all cards</button><button id="queue-previous" title="Previous: K or Left arrow">← Previous</button><button id="queue-resume" title="Resume the next unreviewed item">Resume unreviewed</button><button id="queue-next" title="Next: J or Right arrow">Next →</button><strong id="queue-position">Loading review…</strong><span class="save-state" id="save-state" role="status" aria-live="polite">Loading disk checkpoint…</span><button id="save-now">Save now</button><button id="shortcut-help" title="Keyboard shortcuts (?)">Shortcuts ?</button></div>
<div class="shortcut-strip" aria-label="Keyboard shortcuts"><kbd>G</kbd> good + next <kbd>I</kbd> issue + notes <kbd>R</kbd> recapture + next <kbd>A</kbd> accepted + next <kbd>J</kbd>/<kbd>K</kbd> next/previous <kbd>N</kbd> notes <kbd>Ctrl+Enter</kbd> save note + next</div>
<div class="preset-banner hidden" id="preset-banner"></div>
<div class="layout"><nav class="rail" id="rail"><h2>Coverage</h2></nav><main id="content"></main></div>
<dialog class="lightbox" id="lightbox"><img alt="Expanded audit frame"><p></p></dialog>
<dialog class="shortcut-help" id="shortcut-dialog"><form method="dialog"><button aria-label="Close keyboard help">Close</button></form><h2>Keyboard review</h2><dl><dt><kbd>G</kbd> or <kbd>1</kbd></dt><dd>Looks good, save, and advance</dd><dt><kbd>I</kbd> or <kbd>2</kbd></dt><dd>Flag an issue and focus its notes</dd><dt><kbd>R</kbd> or <kbd>3</kbd></dt><dd>Needs recapture, save, and advance</dd><dt><kbd>A</kbd> or <kbd>4</kbd></dt><dd>Intentional/accepted, save, and advance</dd><dt><kbd>U</kbd> or <kbd>0</kbd></dt><dd>Return to unreviewed</dd><dt><kbd>J</kbd> / <kbd>→</kbd></dt><dd>Next item</dd><dt><kbd>K</kbd> / <kbd>←</kbd></dt><dd>Previous item</dd><dt><kbd>N</kbd></dt><dd>Focus human notes</dd><dt><kbd>Ctrl+Enter</kbd></dt><dd>Save the note to disk and advance</dd><dt><kbd>Esc</kbd></dt><dd>Leave notes or close a dialog</dd></dl><p>Shortcuts pause while typing in a field. Notes autosave as you type.</p></dialog>
<script id="audit-data" type="application/json">{encoded}</script><script src="site.js"></script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--release-receipt", type=Path, default=ROOT / "docs/release/verification/latest.json")
    parser.add_argument("--miniboss-receipt", type=Path)
    parser.add_argument("--pickup-receipt", type=Path)
    parser.add_argument("--projectile-receipt", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--palette-yaml", type=Path, default=DEFAULT_PALETTE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="The Whole Shebang")
    parser.add_argument("--strict", action="store_true", help="fail when any catalog item lacks complete machine evidence")
    args = parser.parse_args()

    evidence_root = args.evidence_root.resolve()
    if not evidence_root.is_dir():
        parser.error(f"evidence root does not exist: {evidence_root}")
    catalog = read_json(args.catalog.resolve())
    palettes = yaml.safe_load(args.palette_yaml.read_text())
    matrix, gate_results, candidate_hash = matrix_context(evidence_root, args.release_receipt.resolve())

    prepare_output(args.output)
    output = args.output.resolve()
    store = MediaStore(output, evidence_root)

    heroes, monsters = build_spotlight(store, evidence_root, candidate_hash, palettes)
    category_items: dict[str, list[dict[str, Any]]] = {
        "stages": build_stages(store, evidence_root, candidate_hash),
        "bosses": build_bosses(store, evidence_root, candidate_hash, catalog, palettes),
        "minibosses": build_minibosses(store, args.miniboss_receipt.resolve() if args.miniboss_receipt else None, candidate_hash),
        "pickups": build_pickups(
            store, evidence_root, candidate_hash, palettes,
            args.pickup_receipt.resolve() if args.pickup_receipt else None,
        ),
        "heroes": heroes,
        "monsters": monsters,
        "projectiles": build_projectiles(store, evidence_root, args.projectile_receipt.resolve() if args.projectile_receipt else None, candidate_hash, catalog, palettes),
        "opening": panel_items(store, evidence_root, "opening-cutscene", "opening", "Opening panel", 33, candidate_hash),
        "pre_final": panel_items(store, evidence_root, "pre-final-inventory", "pre_final", "Pre-final panel", 43, candidate_hash),
        "ending": panel_items(store, evidence_root, "ending-inventory-a", "ending", "Ending panel", 10, candidate_hash),
        "story_keyframes": build_story_keyframes(store, evidence_root, candidate_hash, palettes),
        "secret": build_secret(store, evidence_root, candidate_hash),
        "menus": generic_images(store, evidence_root, "menus", [("menu-icon-palettes", 10)], 10),
        "hazards": build_hazards(store, evidence_root, candidate_hash),
        "title": build_title(store, evidence_root, candidate_hash),
        "death": generic_images(store, evidence_root, "death", [("death-gameover", 12)], 12),
    }

    categories = []
    total_expected = total_covered = failed_categories = 0
    for spec in catalog["categories"]:
        category_id = str(spec["id"])
        items = category_items.get(category_id, [])
        expected = int(spec["expected_items"])
        if len(items) != expected:
            raise RuntimeError(f"catalog/category mismatch for {category_id}: expected {expected}, built {len(items)}")
        gates_pass, missing_gates = gate_ok(gate_results, category_id)
        if not gates_pass:
            for built in items:
                if built["status"] == "covered":
                    built["status"] = "partial"
                built["machine_notes"].append("Suite gate missing/not passed: " + ", ".join(missing_gates))
        covered = sum(row["status"] == "covered" for row in items)
        missing = expected - covered
        total_expected += expected
        total_covered += covered
        failed_categories += bool(missing)
        categories.append({
            **spec,
            "description": f"{covered}/{expected} items have complete hash-bound machine evidence. Human verdicts are stored locally and exportable.",
            "covered_items": covered,
            "missing_items": missing,
            "items": items,
        })

    intentional_blank_sources = {
        str(source): str(reason)
        for source, reason in catalog.get("intentional_blank_sources", {}).items()
    }
    suspicious_set: set[str] = set()
    intentional_uses: dict[str, str] = {}
    for category in categories:
        for built in category["items"]:
            for image in built["images"]:
                blank = (
                    int(image["distinct_colors"]) < 2
                    or float(image["dominant_fraction"]) >= 0.9995
                )
                if not blank:
                    continue
                source = str(image["source"])
                reason = intentional_blank_sources.get(source)
                if reason:
                    image["intentional_blank"] = True
                    image["intentional_reason"] = reason
                    intentional_uses[source] = reason
                    built["machine_notes"].append("Intentional blank: " + reason)
                else:
                    suspicious_set.add(source)
    suspicious = sorted(suspicious_set)
    manifest: dict[str, Any] = {
        "schema": SITE_SCHEMA,
        "status": "complete" if total_covered == total_expected and not suspicious else "gaps",
        "title": args.title,
        "candidate": {
            "sha256": candidate_hash,
            "release_receipt_sha256": digest(args.release_receipt.resolve()),
            "matrix_manifest_sha256": digest(evidence_root.parent / "manifest.json"),
            "matrix_gate_count": len(matrix.get("results", [])),
        },
        "catalog_sha256": digest(args.catalog.resolve()),
        "palette_yaml_sha256": digest(args.palette_yaml.resolve()),
        "supplemental_receipts": {
            key: {
                "path": str(path.resolve()),
                "sha256": digest(path.resolve()),
            }
            for key, path in (
                ("minibosses", args.miniboss_receipt),
                ("pickups", args.pickup_receipt),
                ("projectiles", args.projectile_receipt),
            )
            if path is not None
        },
        "coverage": {
            "expected_items": total_expected,
            "covered_items": total_covered,
            "missing_items": total_expected - total_covered,
            "failed_categories": failed_categories,
        },
        "media": {
            "unique_images": len(store.records),
            "bytes": sum(int(row["size"]) for row in store.records.values()),
            "suspicious_blank_images": suspicious,
            "intentional_blank_images": [
                {"source": source, "reason": reason}
                for source, reason in sorted(intentional_uses.items())
            ],
        },
        "review_presets": catalog.get("review_presets", {}),
        "categories": categories,
    }
    audit_ids = {
        built["audit_id"]
        for category in categories
        for built in category["items"]
    }
    for preset_id, preset in manifest["review_presets"].items():
        rows = preset.get("items", [])
        selected = [str(row.get("audit_id", "")) for row in rows]
        unknown = sorted(set(selected) - audit_ids)
        if unknown:
            raise RuntimeError(
                f"review preset {preset_id} references unknown audit IDs: {unknown}"
            )
        if len(selected) != len(set(selected)):
            raise RuntimeError(f"review preset {preset_id} repeats an audit ID")
    # Gates and intentional-blank classification can append notes after item
    # construction, so bind verdicts only after every visible field is final.
    for category in categories:
        for built in category["items"]:
            built["evidence_sha256"] = item_evidence_digest(built)
    evidence_index = {
        built["audit_id"]: built["evidence_sha256"]
        for category in categories
        for built in category["items"]
    }
    manifest["audit_evidence_sha256"] = hashlib.sha256(
        json.dumps(
            evidence_index, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output / "index.html").write_text(render_html(manifest))
    shutil.copyfile(ASSET_ROOT / "site.css", output / "site.css")
    shutil.copyfile(ASSET_ROOT / "site.js", output / "site.js")

    checksums = []
    for path in sorted(p for p in output.rglob("*") if p.is_file() and p.name not in {"CHECKSUMS.sha256", OWNERSHIP_MARKER}):
        checksums.append(f"{digest(path)}  {path.relative_to(output).as_posix()}")
    (output / "CHECKSUMS.sha256").write_text("\n".join(checksums) + "\n")

    print(json.dumps({
        "status": manifest["status"],
        "candidate_sha256": candidate_hash,
        "coverage": manifest["coverage"],
        "unique_images": manifest["media"]["unique_images"],
        "suspicious_blank_images": suspicious,
        "output": str(output),
    }, indent=2))
    if args.strict and manifest["status"] != "complete":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
