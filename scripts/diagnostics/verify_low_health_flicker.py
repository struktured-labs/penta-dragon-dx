#!/usr/bin/env python3
"""Gate the captured Stage 1 low-health warning path frame by frame."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import zlib

from PIL import Image, ImageChops, ImageStat

from normalize_mgba_state_pc import normalize, png_chunks, write_png


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATE = (
    ROOT / "save_states_for_claude" /
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
)
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_low_health_flicker.lua")
OAM_WRAM_SENTINEL = 0xDF51
SCENE_CACHE_ADDR = 0xDF0D
SERIALIZED_VRAM0 = 0x400
SERIALIZED_VRAM1 = 0x2400
VRAM_MAP_BASES = (0x1800, 0x1C00)
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
CANONICAL_STAGE1_LUT_SHA256 = (
    "487c1443ddec16171cc0f2744b3fbbd013cdcac5e1d7fd8145fe46f277805734"
)
# Same reviewed release table accepted by the captured scene-$0B binder.
RELEASE_STAGE1_LUT_SHA256 = (
    "3b2d1224bb47c68263ff862f1a1c68d8b20f055fe2fcae0fa1028659d492961a"
)
STAGE1_RUNTIME_SOURCE_OFFSETS = (0x37C96, 0x43C96)
STAGE1_RUNTIME_LENGTH = 0x29
ROM_BANK_SIZE = 0x4000
NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR = 0x281C
NEUTRAL_GAMEPLAY_BGP_ROUTINE = bytes.fromhex(
    "3E E4 E0 47 C9 3E E4 E0 47 C9 3E E4 E0 47 C9"
)
R451C_DIRTY_DECIDER = bytes.fromhex(
    "f0b7fe0200c23441f0bab7c2344116df7ceecb5f1afea5200e131a4ff0e5b91b20053e01c361003ea51213f0e5123e01b7c36100c3007e"
)
R453_SHA256 = "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b"
# Exact wrong-destination negative control, not a release candidate. It changes
# only the 12-byte map selector at $4EBD4; all observer ABIs remain identical.
R453_WRONG_DESTINATION_SHA256 = "6699d650947ab2f2f2a601ee85903ad18e7004d4da3098b919ffa499b4334d91"
R456C_PROFILE_SHAS = (
    "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
    "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
    "ccd31659f45da38df7783be3c0d2c6e48f8fb11cc7ab9b5555971df8088eed91",
    "b6d2652e5aed641a2b3bb4f47763ba5fb118ff1d753f6c89f498c95042fd69d9",
    # r527 changes ending-only paths and inherits every observer ABI below.
    "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
    "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
    "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
    "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
    "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
    "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
    "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
    "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
    # Exact menu/title overlay; low-health observer ABI is unchanged.
    "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
    "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
    "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",  # r536: inherited observer/data ABI
    "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b",  # title row guard: unchanged gameplay observer/data ABI
    "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d",  # death/restart successor: unchanged low-health ABI
    "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5",  # #6: unchanged low-health ABI
    "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
    "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
)
R455_SHA256 = "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9"
R455_WRONG_DESTINATION_SHA256 = "22449ff47e9996a578464fbce71ff3339a67f75becd4c47d075dde23034dacc5"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publication_route_profile(rom_bytes: bytes) -> str:
    if hashlib.sha256(rom_bytes).hexdigest() not in {
        R453_SHA256,
        R453_WRONG_DESTINATION_SHA256,
        R455_SHA256, *R456C_PROFILE_SHAS,
        R455_WRONG_DESTINATION_SHA256,
        "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46",
        "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623",
        "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702",
        "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
    }:
        return ""
    offset = 19 * 0x4000 + 0x2B70
    if rom_bytes[19 * 0x4000 + 0x2CCE:19 * 0x4000 + 0x2CD2] != bytes.fromhex("F0 C4 E6 FC"):
        raise ValueError("dispatcher instruction boundary changed")
    if rom_bytes[offset:offset+21] != bytes.fromhex("CB 58 28 06 C3 B7 61 01 02 03 F0 BD FE 03 C2 B7 61 C1 D1 C5 C9"):
        raise ValueError("room03 bypass ABI changed")
    if hashlib.sha256(rom_bytes).hexdigest() in {
            R453_SHA256,
            R453_WRONG_DESTINATION_SHA256,
            R455_SHA256, *R456C_PROFILE_SHAS,
            R455_WRONG_DESTINATION_SHA256,
            "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892"}:
        return "r451c-bounded-room03"
    return "r440-bounded-room03"


def compiler_mapper_sample(row: dict) -> bool:
    return all(row.get(key) == value for key, value in {
        "pc": "09C0", "cpu_a": "01", "stack_return": "4324",
        "rom_bank": "01", "wram_bank": "03",
    }.items())


def publication_routes_exact(counts: dict, profile: str) -> bool:
    dispatches = counts.get("dispatch", 0)
    if not profile:
        return counts.get("pure_helper", 0) == dispatches == counts.get("front", -1)
    if profile == "r451c-bounded-room03":
        return (dispatches > 0
            and counts.get("route_completed", -1)
                + counts.get("route_invalid", -1) == dispatches
            and counts.get("route_invalid", -1) <= 1
            and counts.get("front", -1) == counts.get("route_completed", -2)
            and counts.get("route_pending", -1) == 0)
    return (profile == "r440-bounded-room03" and dispatches > 0
        and counts.get("route_completed", -1) == dispatches
        and counts.get("front", -1) + counts.get("route_bypass", -1) == dispatches
        and counts.get("route_invalid", -1) == 0
        and counts.get("route_pending", -1) == 0)


def owner_address(rom_bytes: bytes) -> int:
    """Select the observed tag only for reviewed exact ROM identities."""
    if hashlib.sha256(rom_bytes).hexdigest() in {
        R453_SHA256,
        R453_WRONG_DESTINATION_SHA256,
        R455_SHA256, *R456C_PROFILE_SHAS,
        R455_WRONG_DESTINATION_SHA256,
        "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46",
        "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702",
        "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623",
        "a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b",
        "9f65073be9326d73b93f9f4279e554791d45279115d450e743b9bc2fa3660567",
        "838110ba5fe8f7aeb1aae470802fdf38b19a0a05e2f6e41e972fc28f68312042",
        "6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c",
        "37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3",
        "06146c7f7f77099c25458843d585abab125439183692c184dff1b2c878a649fd",
        "4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796",
        "24bbce66e2cd0d7c94e032488c18ff1f3946269b61199ffa4ee5d0c1cda1a137",
        "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
    }:
        if rom_bytes[0x42F0:0x42F5] != bytes.fromhex("F0 01 1F 38 07"):
            raise ValueError("r424 owner test instruction mismatch")
        return 0xFF01
    return 0xFFA5


def bulk_compiler_profile(rom_bytes: bytes) -> str:
    if hashlib.sha256(rom_bytes).hexdigest() not in {
        R453_SHA256,
        R453_WRONG_DESTINATION_SHA256,
        R455_SHA256, *R456C_PROFILE_SHAS,
        R455_WRONG_DESTINATION_SHA256,
        "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46",
        "44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702",
        "dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623",
        "6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c",
        "37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3",
        "06146c7f7f77099c25458843d585abab125439183692c184dff1b2c878a649fd",
        "4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796",
        "24bbce66e2cd0d7c94e032488c18ff1f3946269b61199ffa4ee5d0c1cda1a137",
        "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
    }:
        return ""
    import build_stage1_bulk_context_r426 as bulk
    if rom_bytes[0x09BE:0x09C4] != bytes.fromhex("E0 99 EA 00 21 C9"):
        raise ValueError("fixed compiler mapper ABI changed")
    code = bulk.service()
    assert 0x6D00 + len(code) == 0x7890
    start = bulk.prior.OFFSET
    if (rom_bytes[start:start + len(code)] != code
            or rom_bytes[0x4324:0x4328] != bytes.fromhex("3E 01 E0 70")):
        raise ValueError("bulk compiler completion ABI mismatch")
    import build_exact_source_dirty_r385 as dirty
    decider = (R451C_DIRTY_DECIDER
               if hashlib.sha256(rom_bytes).hexdigest()
               in {R453_SHA256, R453_WRONG_DESTINATION_SHA256,
                   R455_SHA256, *R456C_PROFILE_SHAS, R455_WRONG_DESTINATION_SHA256,
                   "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892"}
               else dirty.decider())
    if hashlib.sha256(rom_bytes).hexdigest() == "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46":
        import build_stage1_subscene_tracking_r442 as subscene
        assert decider.startswith(subscene.OLD)
        decider = subscene.NEW + decider[len(subscene.OLD):]
        for offset in subscene.SITES:
            if rom_bytes[offset:offset+5] != subscene.NEW:
                raise ValueError("Stage1 subscene tracking ABI mismatch")
    if hashlib.sha256(rom_bytes).hexdigest() == "24bbce66e2cd0d7c94e032488c18ff1f3946269b61199ffa4ee5d0c1cda1a137":
        import build_warning_source_tracking_r439 as warning
        decider = decider.replace(warning.OLD, warning.NEW)
        for bank, address, original in warning.blocks():
            offset = dirty.offset(bank, address)
            assert rom_bytes[offset:offset+len(original)] == original.replace(warning.OLD, warning.NEW)
    fast = 21 * 0x4000 + 0x100
    fallback = 21 * 0x4000 + 0x3E00
    expected_fallback = bytes.fromhex(
        "16DF7CEECB5F1A4FF04247FA02DCA847FA1BC2A847FAB8C2A8B9"
        "20173C280E131A4FFA00DCB920083E01C361003D18031218061213"
        "FA00DC123E01B7C36100")
    if (rom_bytes[fast:fast + len(decider)] != decider
            or rom_bytes[fallback:fallback + len(expected_fallback)] != expected_fallback):
        raise ValueError("relocated dirty decider ABI mismatch")
    return "r426-bulk-v1"


def copy_boot_state(state: Path, rom: Path, destination: Path) -> dict:
    """Load only an unchanged, exact-ROM boot export; never normalize CPU/VRAM."""
    provenance = json.loads(Path(str(state) + ".json").read_text())
    if provenance.get("schema") != "penta-boot-derived-state-v1":
        raise ValueError("unsupported boot-state provenance")
    for prefix, path in (("rom", rom), ("state", state)):
        if (provenance.get(prefix + "_path") != str(path.resolve())
                or provenance.get(prefix + "_sha256") != digest(path)):
            raise ValueError(f"boot-state {prefix} provenance mismatch")
    report = Path(provenance["report_path"])
    if digest(report) != provenance["report_sha256"]:
        raise ValueError("boot-state report provenance mismatch")
    probe = Path(__file__).with_name("probe_stage1_natural_menu_bg.lua")
    if digest(probe) != provenance["probe_sha256"]:
        raise ValueError("boot-state producer changed; regenerate export")
    destination.write_bytes(state.read_bytes())
    return {"mode": "exact-boot-state", "normalization_writes": 0,
            "provenance": provenance}


def copy_hazard_boot_state(state: Path, rom: Path, destination: Path,
                           receipt_path: Path) -> dict:
    """Accept a freshly produced hazard-route state without machine edits."""
    provenance = json.loads(receipt_path.read_text())
    mutation_fixture = provenance.get("schema") == (
        "penta-stage1-hazard-state-mutation-fixture-v1"
    )
    if ((provenance.get("schema") != "penta-stage1-hazard-state-v1"
         and not mutation_fixture)
            or provenance.get("passed") is not True):
        raise ValueError("hazard-state generation did not pass")
    for name, path in (("rom", rom), ("state", state)):
        if (provenance.get(name) != str(path.resolve())
                or provenance.get(name + "_sha256") != digest(path)):
            raise ValueError(f"hazard-state {name} provenance mismatch")
    if mutation_fixture:
        mutation = provenance.get("mutation_fixture", {})
        if (mutation.get("source_rom_sha256") != provenance.get("source_rom_sha256")
                or mutation.get("kind") != "exact-destination-negative-control"
                or mutation.get("state_sha256") != digest(state)):
            raise ValueError("mutation-fixture provenance mismatch")
    for name, filename in (("generator", "generate_stage1_hazard_state.py"),
                           ("probe", "probe_stage1_north_integrity.lua")):
        if provenance.get(name + "_sha256") != digest(Path(__file__).with_name(filename)):
            raise ValueError("hazard-state producer changed; regenerate state")
    # Validate the observed receipt coverage directly.  Some current-route
    # generators intentionally request a small minimum while recording a
    # much larger settled corpus; rejecting those declarations would discard
    # otherwise fresh, exact evidence.  The publication gate still requires
    # the established absolute coverage floor here.
    if (provenance.get("hardware", {}).get("settled") is not True
            or provenance.get("hazard_cells", 0) < 40
            or provenance.get("tooth_cells", 0) < 10
            or provenance.get("hazard_cells", 0) < provenance.get("minimum_hazard_cells", 0)
            or provenance.get("tooth_cells", 0) < provenance.get("minimum_tooth_cells", 0)):
        raise ValueError("hazard-state coverage or settled hardware missing")
    destination.write_bytes(state.read_bytes())
    return {"mode": "exact-hazard-boot-state", "normalization_writes": 0,
            "receipt_path": str(receipt_path.resolve()),
            "receipt_sha256": digest(receipt_path), "provenance": provenance}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def counter_receipt(path: Path) -> dict[str, int]:
    counters: dict[str, int] = {}
    for line in path.read_text().splitlines():
        name, value = line.split("=", 1)
        counters[name] = int(value)
    return counters


def text_receipt(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def ffe5_room01_observation(
    frames: list[dict[str, str]],
    *,
    incoming_room: str = "01",
    lookback: int = 16,
) -> dict[str, object]:
    """Record the native incoming/effective-room lead before room commit.

    The causal r310 trace shows FFE5=$01 for four rendered samples while FFBD
    still names outgoing room $12, then both remain $01 after commit.  This is
    evidence for the native prepublication selector used by the ROM fix.  It
    is intentionally reported rather than treated as a standalone visual
    oracle: displayed attributes are owned by completed physical-map
    publications, not by either live room byte.
    """
    first_index = next(
        (
            index
            for index, row in enumerate(frames)
            if row.get("room") == incoming_room
        ),
        None,
    )
    room_frames = [
        row for row in frames if row.get("room") == incoming_room
    ]
    precommit_frames: list[dict[str, str]] = []
    if first_index is not None:
        precommit_frames = [
            row
            for row in frames[max(0, first_index - lookback):first_index]
            if row.get("room") != incoming_room
            and row.get("ffe5") == incoming_room
        ]
    mismatches = [
        row for row in room_frames if row.get("ffe5") != incoming_room
    ]
    return {
        "incoming_room": incoming_room,
        "lookback_samples": lookback,
        "first_committed_sample": (
            int(room_frames[0]["sample"]) if room_frames else None
        ),
        "precommit_samples": [
            int(row["sample"]) for row in precommit_frames
        ],
        "committed_room_samples": len(room_frames),
        "committed_room_key_mismatches": len(mismatches),
        "supports_prepublication_selector": (
            bool(precommit_frames)
            and bool(room_frames)
            and not mismatches
        ),
    }


def resident_compiler_counter_contract(
    counters: dict[str, int], *, prefix: str = "",
) -> bool:
    """Require exact 24-row use of the reviewed SVBK3:D400 compiler."""
    publications = counters.get(f"{prefix}compiler_publications", 0)
    rows = counters.get(f"{prefix}compiler_row_calls", 0)
    first_rows = counters.get(f"{prefix}compiler_first_rows", 0)
    mismatches = counters.get(
        f"{prefix}compiler_contract_mismatches", -1
    )
    return (
        publications > 0
        and first_rows == publications
        and rows == publications * 24
        and mismatches == 0
    )


def authenticated_compiler_counter_contract(counters, profile, *, prefix=""):
    if not profile:
        return resident_compiler_counter_contract(counters, prefix=prefix)
    if profile != "r426-bulk-v1":
        return False
    publications = counters.get(prefix + "compiler_publications", 0)
    return (publications > 0
            and counters.get(prefix + "bulk_completions", -1) == publications
            and counters.get(prefix + "bulk_mismatches", -1) == 0
            and counters.get(prefix + "compiler_row_calls", -1) == 0
            and counters.get(prefix + "compiler_first_rows", -1) == 0
            and counters.get(prefix + "compiler_contract_mismatches", -1) == 0)


def normalize_fixture_attrs(state: Path, rom: Path) -> dict[str, int]:
    """Compile both legacy maps through the LUT plus exact hazard geometry.

    The checked-in hazard state predates semantic attributes and serializes
    most offscreen cells as palette zero. Runtime settling repairs active
    semantic cells, but deliberately does not broad-sweep ordinary walls
    because that was the source of the miniboss flicker regression. Normalize
    only the test input here from the candidate's raw-attribute LUT, then
    require zero semantic drift for the complete soak.

    The retired normalizer inferred a whole rotating span and forced every
    cell to $0F. That recreated the yellow-trail bug this gate must reject.
    Its replacement then trusted the global LUT for teeth too, which became
    equally wrong once the production fix deliberately confined VRAM-bank 1
    to real hazard geometry: it changed valid fixture teeth back to gray BG7
    before the emulator even started.  The LUT remains authoritative for the
    palette bits.  The same fail-closed row discriminators used by the live
    receipt add bit 3 only to actual $64-$69/$74-$79 tooth cells inside a
    reviewed cylinder row; reused tile IDs elsewhere stay in bank 0.
    """
    chunks = png_chunks(state.read_bytes())
    indices = [
        index for index, (kind, _) in enumerate(chunks) if kind == b"gbAs"
    ]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    rom_bytes = rom.read_bytes()
    table = rom_bytes[STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 0x100]
    if len(table) != 0x100:
        raise RuntimeError("candidate Stage-1 LUT is incomplete")
    def tooth(tile: int) -> bool:
        folded = tile & 0xEF
        return 0x64 <= folded < 0x6A

    changed: dict[str, int] = {}
    for base in VRAM_MAP_BASES:
        tiles = raw[SERIALIZED_VRAM0 + base:SERIALIZED_VRAM0 + base + 0x400]
        expected_attrs = bytearray(table[tile] & 0x07 for tile in tiles)
        for row in range(32):
            row_start = row * 32
            row_tiles = tiles[row_start:row_start + 32]
            hazard_columns: range | tuple[int, ...] = ()
            if tooth(row_tiles[0]) or tooth(row_tiles[1]):
                width = 11 if tooth(row_tiles[10]) else (
                    10 if tooth(row_tiles[9]) else 9
                )
                hazard_columns = range(width)
            elif row_tiles[4] == 0x6A:
                hazard_columns = range(5, 15)
            elif tooth(row_tiles[4]) or tooth(row_tiles[5]):
                hazard_columns = range(4, 13)
            elif tooth(row_tiles[6]):
                # Alternating translated phase: only the actual tooth cells,
                # never the intervening neutral gaps, own immutable bank 1.
                hazard_columns = tuple(
                    column for column in range(4, 14)
                    if tooth(row_tiles[column])
                )
            for column in hazard_columns:
                offset = row_start + column
                if tooth(tiles[offset]):
                    if expected_attrs[offset] != 0x07:
                        raise RuntimeError(
                            f"hazard tooth ${tiles[offset]:02X} is not BG7"
                        )
                    expected_attrs[offset] = 0x0F
        count = 0
        for offset in range(0x400):
            attr_offset = SERIALIZED_VRAM1 + base + offset
            expected = expected_attrs[offset]
            count += raw[attr_offset] != expected
            raw[attr_offset] = expected
        changed[f"{0x8000 + base:04X}"] = count
    # Bind the cross-version fixture to this ROM's immutable hazard art too.
    # Otherwise forcing the runtime loader to refresh an old savestate races
    # its first already-in-flight map publication: that publication correctly
    # skips the geometry writer until all three art DMAs finish, but no second
    # map copy is guaranteed while the fixture is intentionally stationary.
    art_regions = (
        # bank, source, VRAM destination, byte count
        (14, 0x6C10, 0x9010, 0x40),
        (7, 0x5740, 0x9640, 0x60),
        (7, 0x57A0, 0x9740, 0x60),
    )
    art_changes = 0
    for bank, source, destination, size in art_regions:
        source_offset = bank * ROM_BANK_SIZE + source - 0x4000
        payload = rom_bytes[source_offset:source_offset + size]
        if len(payload) != size:
            raise RuntimeError("candidate hazard-art source is incomplete")
        destination_offset = SERIALIZED_VRAM1 + destination - 0x8000
        old = raw[destination_offset:destination_offset + size]
        art_changes += sum(left != right for left, right in zip(old, payload))
        raw[destination_offset:destination_offset + size] = payload
    changed["bank1_hazard_art"] = art_changes
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(state, chunks)
    return changed


def frame_metrics(paths: list[Path]) -> dict[str, object]:
    near_white = []
    white = []
    means = []
    changed_pixels = []
    mean_rgb_deltas = []
    previous = None
    for path in paths:
        with Image.open(path) as source:
            image = source.convert("RGB")
            pixels = list(image.getdata())
        if previous is not None:
            difference = ImageChops.difference(image, previous)
            changed_pixels.append(sum(
                pixel != (0, 0, 0) for pixel in difference.getdata()
            ))
            mean_rgb_deltas.append(sum(ImageStat.Stat(difference).mean) / 3)
        previous = image
        near_white.append(sum(
            red >= 224 and green >= 224 and blue >= 224
            for red, green, blue in pixels
        ))
        white.append(sum(
            red >= 248 and green >= 248 and blue >= 248
            for red, green, blue in pixels
        ))
        means.append(sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3))
    median_near_white = statistics.median(near_white)
    median_mean = statistics.median(means)
    local_near_white_spikes = [
        near_white[index] - max(near_white[index - 1], near_white[index + 1])
        for index in range(1, len(near_white) - 1)
    ]
    local_luma_spikes = [
        means[index] - max(means[index - 1], means[index + 1])
        for index in range(1, len(means) - 1)
    ]
    return {
        "frames": len(paths),
        "near_white_min": min(near_white),
        "near_white_median": median_near_white,
        "near_white_max": max(near_white),
        "near_white_max_above_median": max(near_white) - median_near_white,
        "white_min": min(white),
        "white_max": max(white),
        "mean_luma_min": round(min(means), 3),
        "mean_luma_median": round(median_mean, 3),
        "mean_luma_max": round(max(means), 3),
        "mean_luma_max_above_median": round(max(means) - median_mean, 3),
        "single_frame_near_white_spike_max": max(
            local_near_white_spikes, default=0
        ),
        "single_frame_luma_spike_max": round(
            max(local_luma_spikes, default=0), 3
        ),
        "successive_changed_pixels_max": max(changed_pixels, default=0),
        "successive_changed_pixels_max_sample": (
            changed_pixels.index(max(changed_pixels)) + 2
            if changed_pixels else 0
        ),
        "successive_mean_rgb_delta_max": round(
            max(mean_rgb_deltas, default=0), 3
        ),
        "successive_mean_rgb_delta_max_sample": (
            mean_rgb_deltas.index(max(mean_rgb_deltas)) + 2
            if mean_rgb_deltas else 0
        ),
    }


def hazard_attributes_clean(sample_rows: list[dict[str, str]]) -> bool:
    """Reject one semantically wrong rotating-hazard frame."""
    return all(
        row["unexpected_mismatches"] == "0" for row in sample_rows
    )


def publication_owner_handoffs(
    sample_rows: list[dict[str, str]],
) -> dict[str, object]:
    """Prove a register-only room handoff cannot relabel an unchanged map."""
    handoffs = []
    for previous, current in zip(sample_rows, sample_rows[1:]):
        if (
            previous.get("room") == current.get("room")
            or previous.get("map") != current.get("map")
            or previous.get("tile_bytes") != current.get("tile_bytes")
            or previous.get("attr_bytes") != current.get("attr_bytes")
        ):
            continue
        exact = (
            previous.get("map_owner_valid") == "1"
            and current.get("map_owner_valid") == "1"
            and previous.get("map_owner_epoch")
            == current.get("map_owner_epoch")
            and previous.get("unexpected_mismatches") == "0"
            and current.get("unexpected_mismatches") == "0"
        )
        handoffs.append({
            "from_sample": int(previous["sample"]),
            "to_sample": int(current["sample"]),
            "from_room": previous["room"],
            "to_room": current["room"],
            "map": current["map"],
            "owner_epoch": int(current.get("map_owner_epoch", "0")),
            "exact": exact,
        })
    return {
        "count": len(handoffs),
        "exact": bool(handoffs) and all(row["exact"] for row in handoffs),
        "handoffs": handoffs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--boot-derived-state", action="store_true",
                        help="require exact-ROM export provenance and skip all state normalization")
    parser.add_argument("--hazard-state-receipt", type=Path,
                        help="with --boot-derived-state, load a current cold-route hazard-state receipt")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "tmp/penta-low-health-flicker")
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--settle", type=int, default=120)
    parser.add_argument("--settle-keys", type=lambda value: int(value, 0), default=0,
                        help="Normal input during settling until the displayed map has an observed publication")
    parser.add_argument("--settle-drive-frames", type=int, default=0,
                        help="Continue settling input for this fixed frame count to reach hazard coverage")
    parser.add_argument("--samples", type=int, default=240)
    parser.add_argument(
        "--pre-trigger", type=int, default=60,
        help=(
            "captured healthy frames before forcing the fixture across the "
            "low-health/music-warning threshold and applying movement"
        ),
    )
    parser.add_argument(
        "--require-scene0b-low-health", action="store_true",
        help=(
            "exercise the real DCBB -> DD06 -> D880=$0B low-health "
            "override and require its Stage-1 publication route"
        ),
    )
    parser.add_argument(
        "--scene0b-frames", type=int, default=120,
        help=(
            "bounded native DCBB=$40 warning window before restoring DCBB "
            "(default: 120 sampled frames)"
        ),
    )
    parser.add_argument(
        "--post-trigger-keys", type=lambda value: int(value, 0), default=0,
        help="input mask held after the deterministic health transition",
    )
    parser.add_argument("--recovery-drive-frames", type=int, default=0,
                        help="resume the input mask for this many native recovery frames")
    parser.add_argument(
        "--require-music-transition", action="store_true",
        help=(
            "require the Stage-1 to Gargoyle scene/song transition and its "
            "native $FFF7 pulse countdown while health is low"
        ),
    )
    parser.add_argument(
        "--require-pulse-countdown", action="store_true",
        help="also require the forced fixture to observe FFF7 count to zero",
    )
    parser.add_argument(
        "--require-hazard-attributes", action="store_true",
        help=(
            "require exact raw attrs for teeth, neutral gaps, body, support, "
            "and endpoints on every rendered frame"
        ),
    )
    parser.add_argument(
        "--require-hazard-publication-owner", action="store_true",
        help=(
            "require every completed Stage-1 hazard publication to enter "
            "the geometry scanner and reach its semantic row writer"
        ),
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--state-out",
        type=Path,
        help=(
            "save the final candidate-owned machine state for a chained "
            "deterministic verifier"
        ),
    )
    parser.add_argument(
        "--diagnose-compiler-hang",
        action="store_true",
        help=(
            "arm a fail-closed HDMA launch/wait watchdog and preserve an "
            "exact machine-state trace if the publisher stops making progress"
        ),
    )
    parser.add_argument(
        "--trace-scanner",
        action="store_true",
        help="record the bank-qualified Stage-1 scanner/writer route",
    )
    args = parser.parse_args()
    if args.recovery_drive_frames and not args.require_scene0b_low_health:
        parser.error("--recovery-drive-frames requires the scene0b profile")
    if (args.recovery_drive_frames < 0 or (args.recovery_drive_frames > 0
            and args.recovery_drive_frames > args.samples - args.pre_trigger - args.scene0b_frames)):
        parser.error("recovery drive must fit the sampled recovery window")
    if not 0 <= args.post_trigger_keys <= 0xFF:
        parser.error("--post-trigger-keys must fit the eight-button input mask")
    if args.hazard_state_receipt and not args.boot_derived_state:
        parser.error("--hazard-state-receipt requires --boot-derived-state")
    if not 0 <= args.settle_drive_frames <= args.settle:
        parser.error("--settle-drive-frames must be between zero and --settle")
    if not 0 <= args.settle_keys <= 0xFF:
        parser.error("--settle-keys must fit the eight-button input mask")
    if args.require_scene0b_low_health and not (
        0 < args.pre_trigger
        and args.scene0b_frames > 0
        and args.pre_trigger + args.scene0b_frames < args.samples
    ):
        parser.error(
            "scene-$0B profile requires pre-trigger + scene0b-frames < samples"
        )
    if (args.require_scene0b_low_health
            and not args.require_hazard_publication_owner):
        parser.error(
            "scene-$0B profile requires --require-hazard-publication-owner"
        )
    if args.require_scene0b_low_health and args.require_music_transition:
        parser.error(
            "scene-$0B and Gargoyle-music profiles are separate gates"
        )
    rom_bytes = args.rom.read_bytes()
    canonical_stage1_lut = rom_bytes[
        STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 0x100
    ]
    canonical_stage1_lut_sha256 = hashlib.sha256(
        canonical_stage1_lut
    ).hexdigest()
    if (
        len(canonical_stage1_lut) != 0x100
        or canonical_stage1_lut_sha256 not in {
            CANONICAL_STAGE1_LUT_SHA256, RELEASE_STAGE1_LUT_SHA256,
            # r438 changes only twelve tooth bank bits; low palette bits
            # remain identical. Hazard bank selection is independently graded.
            "22de0c9f11d8b8f4f050c4e62928e7ea300b1d7483fb9df1d65bb6eec6a0527f"}
    ):
        parser.error(
            "candidate Stage-1 LUT is not the reviewed canonical semantic "
            f"table ({canonical_stage1_lut_sha256})"
        )

    args.output.mkdir(parents=True, exist_ok=True)
    canonical_lut_path = args.output / "canonical-stage1-lut.bin"
    canonical_lut_path.write_bytes(canonical_stage1_lut)
    prefix = args.output / "low-health"
    for path in args.output.glob("low-health.*"):
        path.unlink()
    normalized = args.output / "low-health-current.ss0"
    runtime_images = [
        rom_bytes[offset:offset + STAGE1_RUNTIME_LENGTH]
        for offset in STAGE1_RUNTIME_SOURCE_OFFSETS
    ]
    if any(len(image) != STAGE1_RUNTIME_LENGTH for image in runtime_images):
        parser.error("candidate ROM is missing a Stage-1 DAD7 runtime source")
    runtime_paths = []
    for index, image in enumerate(runtime_images, start=1):
        path = args.output / f"candidate-stage1-runtime-{index}.bin"
        path.write_bytes(image)
        runtime_paths.append(path)
    # Cross-ROM fixtures serialize the old candidate's executable DAxx/DBxx
    # helpers and an obsolete title-card scene cache. Force the existing
    # sentinel-gated initializer to refresh the helpers, and bind the cached
    # scene to this fixture's actual live D880=$02 identity. Otherwise a state
    # captured by an older build can replay a title transition before sampling
    # and perturb the very gameplay cadence this receipt is meant to compare.
    if args.boot_derived_state:
        if args.hazard_state_receipt:
            fixture_attr_normalization = copy_hazard_boot_state(
                args.state.resolve(), args.rom.resolve(), normalized,
                args.hazard_state_receipt.resolve())
        else:
            fixture_attr_normalization = copy_boot_state(
                args.state.resolve(), args.rom.resolve(), normalized)
    else:
        normalize(
        args.state.resolve(), normalized, 0x016C,
        [
            (OAM_WRAM_SENTINEL, 0),
            # normalize_fixture_attrs also installs this candidate's exact
            # immutable bank-1 art, so publish the completed three-DMA state
            # and test low-health behavior rather than a fixture-loader race.
            (0xDF5B, 3),
            (SCENE_CACHE_ADDR, 0x02),
            # Bind the live scene register to the exact Stage-1 fixture as
            # the chained hazard/menu gates do.  The old cross-ROM state can
            # retain room-$01/title scene $01 even after its cache is fixed,
            # which makes the low-health transition test a stale-state test.
            (0xD880, 0x02),
            # This is a live-play health/music fixture.  Old captures can
            # serialize the prerecorded-route discriminator as zero, which
            # intentionally disables the live hazard post-copy owner.
            (0xDCFD, 1),
            # The accepted always-mapped post-copy guard uses FFBA=0 as the
            # exact Stage-1 authority.  Old captures can retain a later-stage
            # selector here even though D880/room data are Stage 1.
            (0xFFBA, 0),
        ],
        args.rom.resolve(),
    )
        fixture_attr_normalization = normalize_fixture_attrs(
            normalized, args.rom.resolve()
        )

    environment = os.environ.copy()
    environment.update({
        # r424's fixed $42F0 loads FF01, not the retired FFA5 owner byte.
        # Bind this observer ABI to the entire ROM, not a caller override.
        "LOW_HEALTH_OWNER_ADDRESS": str(owner_address(rom_bytes)),
        "LOW_HEALTH_BULK_COMPILER": bulk_compiler_profile(rom_bytes),
        "LOW_HEALTH_PUBLICATION_ROUTE_PROFILE": publication_route_profile(rom_bytes),
        "LOW_HEALTH_DMA_SITES": ",".join(
            f"{offset // 0x4000}:{offset if offset < 0x4000 else 0x4000 + offset % 0x4000}"
            for offset in range(len(rom_bytes) - 1)
            if rom_bytes[offset:offset + 2] == bytes.fromhex("E0 55")
        ) if environment.get("LOW_HEALTH_TRACE_ATTR") == "1" else "",
        "LOW_HEALTH_STORE_SITES": ",".join(
            f"{offset // 0x4000}:{0x4000 + offset % 0x4000}:{rom_bytes[offset]}"
            for offset in range(len(rom_bytes))
            if offset // 0x4000 in (13, 16, 19, 20, 21)
            and rom_bytes[offset] in (0x12, 0x22, 0x77)
        ) if environment.get("LOW_HEALTH_TRACE_STORES") == "1" else "",
        "LOW_HEALTH_BOOT_STATE": "1" if args.boot_derived_state else "0",
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "LOW_HEALTH_OUT": str(prefix),
        "LOW_HEALTH_SETTLE": str(args.settle),
        "LOW_HEALTH_SETTLE_KEYS": str(args.settle_keys),
        "LOW_HEALTH_SETTLE_DRIVE_FRAMES": str(args.settle_drive_frames),
        "LOW_HEALTH_SAMPLES": str(args.samples),
        "LOW_HEALTH_PRE_TRIGGER": str(args.pre_trigger),
        "LOW_HEALTH_POST_TRIGGER_KEYS": str(args.post_trigger_keys),
        "LOW_HEALTH_RECOVERY_DRIVE_FRAMES": str(args.recovery_drive_frames),
        "LOW_HEALTH_REQUIRE_SCENE0B": (
            "1" if args.require_scene0b_low_health else "0"
        ),
        "LOW_HEALTH_SCENE0B_FRAMES": str(args.scene0b_frames),
        "LOW_HEALTH_RUNTIME_A": str(runtime_paths[0]),
        "LOW_HEALTH_RUNTIME_B": str(runtime_paths[1]),
        "LOW_HEALTH_CANONICAL_LUT": str(canonical_lut_path),
    })
    if args.state_out is not None:
        args.state_out.parent.mkdir(parents=True, exist_ok=True)
        args.state_out.unlink(missing_ok=True)
        environment["LOW_HEALTH_STATE_OUT"] = str(args.state_out.resolve())
    if args.require_hazard_attributes or args.require_hazard_publication_owner:
        environment["LOW_HEALTH_TRACE_LAYOUTS"] = "1"
    if args.trace_scanner:
        environment["LOW_HEALTH_TRACE_SCANNER"] = "1"
    if args.diagnose_compiler_hang:
        environment["LOW_HEALTH_WATCH_COMPILER_HANG"] = "1"
        environment["LOW_HEALTH_DIAGNOSTIC_LIGHT"] = "1"
    log = args.output / "mgba.log"
    with log.open("w") as stream:
        completed = subprocess.run(
            [
                str(args.mgba.resolve()), "--fastforward", "-t",
                str(normalized), "--script", str(PROBE),
                str(args.rom.resolve()),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )
    marker = Path(str(prefix) + ".done")
    watchdog = Path(str(prefix) + ".compiler-watchdog.tsv")
    wedged = Path(str(prefix) + ".compiler-watchdog.wedged")
    if args.diagnose_compiler_hang:
        if wedged.is_file():
            print(f"FAIL: guarded publisher watchdog tripped; see {watchdog}")
            return 2
        if completed.returncode == 0 and marker.is_file():
            print(
                "PASS: diagnostic route completed without a compiler/postcopy "
                f"hang; trace: {watchdog}"
            )
            return 0
    if completed.returncode != 0 or not marker.is_file():
        print(f"FAIL: mGBA status {completed.returncode}; see {log}")
        return 1
    if args.state_out is not None and not args.state_out.is_file():
        print(f"FAIL: requested chained state was not written: {args.state_out}")
        return 1

    scanner_counts = (
        counter_receipt(Path(str(prefix) + ".scanner-counts.txt"))
        if args.require_hazard_publication_owner else {}
    )
    fixture_tooth_rebind = counter_receipt(
        Path(str(prefix) + ".fixture-tooth-rebind.txt")
    )
    runtime_receipt = text_receipt(
        Path(str(prefix) + ".runtime.txt")
    )

    frames = rows(Path(str(prefix) + ".frames.tsv"))
    writes = rows(Path(str(prefix) + ".writes.tsv"))
    screenshots = sorted(args.output.glob("low-health.frame*.png"))
    metrics = frame_metrics(screenshots)
    sampled_frame_numbers = {int(row["frame"]) for row in frames}
    sampled_writes = [
        row for row in writes if int(row["frame"]) in sampled_frame_numbers
    ]
    bad_writes = [row for row in sampled_writes if row["new"] != "E4"]
    dma_unreadable = [
        row for row in frames if row.get("dma_unreadable") == "1"
    ]
    compiler_unreadable = [
        row for row in frames if row.get("compiler_unreadable") == "1"
    ]
    readable_frames = [
        row for row in frames
        if row.get("dma_unreadable") == "0"
        and row.get("compiler_unreadable") == "0"
    ]
    pre_frames = [
        row for row in readable_frames if row["health_phase"] == "pre"
    ]
    low_frames = [
        row for row in readable_frames if row["health_phase"] == "low"
    ]
    scene0b_frames = [
        row for row in readable_frames if row["d880"] == "0B"
    ]
    scene0b_stimulus_frames = [
        row for row in readable_frames
        if row.get("stimulus_phase") == "scene0b"
    ]
    active_scene0b_frames = [
        row for row in scene0b_stimulus_frames if row["d880"] == "0B"
    ]
    pre_stimulus_frames = [
        row for row in readable_frames
        if row.get("stimulus_phase") == "pre"
    ]
    recovered_frames = [
        row for row in readable_frames
        if row.get("stimulus_phase") == "recovered"
    ]
    hazard_mismatch_frames = [
        row for row in readable_frames
        if int(row["unexpected_mismatches"]) > 0
    ]
    publication_owner_missing_frames = [
        row for row in readable_frames
        if row.get("map_owner_valid") != "1"
        or int(row.get("oracle_missing", "1")) != 0
        or int(row.get("map_owner_epoch", "0")) <= 0
        or int(row.get("map_owner_frame", "0")) > int(row["frame"])
    ]
    publication_owner_maps = {
        row["map"] for row in readable_frames
        if row.get("map_owner_valid") == "1"
    }
    room_register_handoffs = publication_owner_handoffs(readable_frames)
    scene_values = [row["d880"] for row in readable_frames]
    music_transition_sample = next((
        int(row["sample"]) for row in readable_frames if row["d880"] == "0A"
    ), 0)
    pulse_values = [int(row["fff7"], 16) for row in readable_frames]
    post_music_pulse_values = [
        int(row["fff7"], 16)
        for row in readable_frames
        if int(row["sample"]) >= music_transition_sample
    ] if music_transition_sample else []
    cram_values = {row["bg_cram"] for row in readable_frames}
    attr_layouts = {
        map_name: {
            row["attr_bytes"]
            for row in readable_frames
            if row["map"] == map_name
        }
        for map_name in {row["map"] for row in readable_frames}
    }
    runtime_source = runtime_receipt.get("matched_source", "none")
    runtime_mismatches = {
        "bank13": int(runtime_receipt.get("mismatch_bank13", "999")),
        "bank16": int(runtime_receipt.get("mismatch_bank16", "999")),
    }
    try:
        runtime_actual = bytes.fromhex(runtime_receipt.get("actual_hex", ""))
    except ValueError:
        runtime_actual = b""
    runtime_bound = (
        runtime_source in {"bank13", "bank16"}
        and runtime_mismatches[runtime_source] == 0
        and len(runtime_actual) == STAGE1_RUNTIME_LENGTH
        and runtime_actual == runtime_images[
            0 if runtime_source == "bank13" else 1
        ]
    )
    checks = {
        "all requested consecutive frames captured": (
            args.samples <= len(frames) <= args.samples + 8
            and len(frames) == len(screenshots)
            and [int(row["sample"]) for row in frames]
                == list(range(1, len(frames) + 1))
            and [int(row["frame"]) for row in frames]
                == list(range(args.settle + 1, args.settle + len(frames) + 1))
        ),
        "DMA-unreadable samples are exactly classified by HRAM PC/source": (
            all(
                0xFF80 <= int(row["pc"], 16) <= 0xFF9F
                and row["dma_source"] in {"C0", "C1"}
                and row["d880"] == "FF"
                for row in dma_unreadable
            )
        ),
        "private-WRAM compiler samples are exactly classified by PC/SVBK": (
            len(readable_frames) + len(dma_unreadable)
            + len(compiler_unreadable) == len(frames)
            and all(
                (
                    row.get("wram_bank") == "03"
                    and (
                        (row.get("rom_bank") == "01" and (
                            0x42A7 <= int(row["pc"], 16) <= 0x436D
                            or 0xD400 <= int(row["pc"], 16) <= 0xD478))
                        or (bulk_compiler_profile(rom_bytes) == "r426-bulk-v1"
                            and row.get("rom_bank") == "1E"
                            and 0x6D00 <= int(row["pc"], 16) < 0x7890)
                        or (bulk_compiler_profile(rom_bytes) == "r426-bulk-v1"
                            and compiler_mapper_sample(row))
                    )
                )
                for row in compiler_unreadable
            )
        ),
        "resident DAD7 helper matches an exact candidate source": runtime_bound,
        "fixture stays in live Stage 1/Gargoyle gameplay": all(
            row["d880"] in (
                (
                    {"02", "0B"}
                    if args.require_scene0b_low_health
                    else {"02", "0A"}
                    if args.require_music_transition
                    else {"02"}
                )
            )
            and row["ffc1"] == "01"
            for row in readable_frames
        ),
        "fixture crosses the low-health warning threshold once": (
            args.require_scene0b_low_health
            or (
            0 < args.pre_trigger < args.samples
            and len(pre_frames) >= (
                args.pre_trigger
                - len(dma_unreadable)
                - len(compiler_unreadable)
            )
            and len(low_frames) >= (
                args.samples - args.pre_trigger
                - len(dma_unreadable)
                - len(compiler_unreadable)
            )
            and all(row["hp_main"] == "01" for row in pre_frames)
            and all(row["hp_main"] == "00" for row in low_frames)
            )
        ),
        "BGP remains normal E4 at every rendered frame": all(
            row["bgp"] == "E4" for row in frames
        ),
        "gameplay pulse writers are statically neutralized to E4": (
            rom_bytes[
                NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR:
                NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR
                + len(NEUTRAL_GAMEPLAY_BGP_ROUTINE)
            ] == NEUTRAL_GAMEPLAY_BGP_ROUTINE
        ),
        "hazard bank bits occur only at exact Stage-1 tooth travel cells": (
            all(row["unsafe"] == "0" for row in readable_frames)
            and max(
                (int(row["approved_bank1"]) for row in readable_frames),
                default=0,
            ) > 0
        ),
        "visible non-tooth attributes never expose unsafe high bits": all(
            row["unsafe"] == "0" for row in readable_frames
        ),
        "BG CRAM is byte-stable after settling": len(cram_values) == 1,
        "no rendered near-white flash outlier": (
            (
                args.post_trigger_keys == 0
                and metrics["near_white_max_above_median"] < 6000
                and metrics["mean_luma_max_above_median"] < 35
            )
            or (
                args.post_trigger_keys != 0
                and metrics["single_frame_near_white_spike_max"] < 1500
                and metrics["single_frame_luma_spike_max"] < 8
            )
        ),
        "no rendered whole-background discontinuity at warning transition": (
            metrics["successive_changed_pixels_max"] < 12000
            and metrics["successive_mean_rgb_delta_max"] < 50
        ),
    }
    first_dd06_sample = 0
    first_scene0b_sample = 0
    first_recovered_sample = 0
    ffe5_observation: dict[str, object] = {
        "incoming_room": "01",
        "lookback_samples": 16,
        "first_committed_sample": None,
        "precommit_samples": [],
        "committed_room_samples": 0,
        "committed_room_key_mismatches": 0,
        "supports_prepublication_selector": False,
    }
    if args.require_scene0b_low_health:
        ffe5_observation = ffe5_room01_observation(
            readable_frames
        )
        first_dd06_sample = next((
            int(row["sample"]) for row in readable_frames
            if row["dd06"] != "00"
        ), 0)
        first_scene0b_sample = next((
            int(row["sample"]) for row in readable_frames
            if row["d880"] == "0B"
        ), 0)
        first_recovered_sample = next((
            int(row["sample"]) for row in recovered_frames
            if row["dd06"] == "00" and row["d880"] == "02"
        ), 0)
        recovery_deadline = (
            args.pre_trigger + args.scene0b_frames + 16
        )
        checks.update({
            "native evaluator orders healthy -> DD06 -> scene $0B": (
                bool(pre_stimulus_frames)
                and all(
                    row["dcbb"] == "FF"
                    and row["dd06"] == "00"
                    and row["d880"] == "02"
                    for row in pre_stimulus_frames
                )
                and first_dd06_sample > args.pre_trigger
                and first_scene0b_sample > args.pre_trigger
                and first_dd06_sample <= first_scene0b_sample
                and first_scene0b_sample
                <= args.pre_trigger + min(args.scene0b_frames, 16)
                and len(scene0b_frames) >= min(60, args.scene0b_frames // 2)
                and bool(active_scene0b_frames)
                and all(row["dd06"] == "01"
                        for row in active_scene0b_frames)
            ),
            "scene-$0B window retains exact Stage-1 authority": (
                bool(scene0b_frames)
                and all(
                    row["ffb7"] == "02"
                    and row["ffbf"] == "00"
                    and row["ffba"] == "00"
                    for row in scene0b_frames
                )
            ),
            "bounded DCBB-only stimulus recovers through native state": (
                len(scene0b_stimulus_frames) >= args.scene0b_frames - 16
                and all(row["dcbb"] == "40"
                        for row in scene0b_stimulus_frames)
                and bool(recovered_frames)
                and all(row["dcbb"] == "FF" for row in recovered_frames)
                and first_recovered_sample > (
                    args.pre_trigger + args.scene0b_frames
                )
                and first_recovered_sample <= recovery_deadline
                and all(
                    row["dd06"] == "00" and row["d880"] == "02"
                    for row in recovered_frames[-16:]
                )
            ),
        })
    if args.require_music_transition:
        checks.update({
            "low-health run naturally enters the Gargoyle music scene": (
                bool(scene_values)
                and scene_values[0] == "02"
                and music_transition_sample > args.pre_trigger
                and "0A" in scene_values
            ),
            "music init and warning pulse arm while BGP stays neutral": (
                any(row["d885"] != "00" for row in readable_frames)
                and max(pulse_values, default=0) >= 0x28
                and all(row["bgp"] == "E4" for row in low_frames)
            ),
        })
    if args.require_pulse_countdown:
        checks["forced fixture observes the native pulse countdown to zero"] = (
            args.require_music_transition
            and len(set(post_music_pulse_values)) >= 40
            and max(post_music_pulse_values, default=0) >= 0x27
            and min(post_music_pulse_values, default=0xFF) == 0
        )
    if args.require_hazard_attributes:
        checks.update({
            "rotating-hazard attributes remain semantically correct": (
                hazard_attributes_clean(readable_frames)
            ),
            "every rendered map uses a completed publication-owned oracle": (
                bool(readable_frames)
                and not publication_owner_missing_frames
                and publication_owner_maps == {"9800", "9C00"}
            ),
        })
        if args.require_scene0b_low_health:
            checks[
                "healthy pre-stimulus hazard oracle is already clean"
            ] = (
                bool(pre_stimulus_frames)
                and hazard_attributes_clean(pre_stimulus_frames)
            )
            checks[
                "room-register handoff preserves physical-map oracle epoch"
            ] = (
                room_register_handoffs["exact"]
                or (
                    hashlib.sha256(rom_bytes).hexdigest() in {
                    R453_SHA256,
                    R453_WRONG_DESTINATION_SHA256,
                    R455_SHA256, *R456C_PROFILE_SHAS,
                    R455_WRONG_DESTINATION_SHA256,
                    "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892"}
                    and room_register_handoffs["count"] == 0
                    and ffe5_observation["first_committed_sample"] == 1
                    and ffe5_observation["committed_room_key_mismatches"] == 0
                )
            )
    if args.require_hazard_publication_owner:
        publications = scanner_counts.get("postcopy", 0)
        dispatches = scanner_counts.get("dispatch", 0)
        scanner_entries = scanner_counts.get("front", 0)
        semantic_writes = scanner_counts.get("write", 0)
        pure_copies = scanner_counts.get("pure_copy", 0)
        dirty_copies = scanner_counts.get("dirty_copy", 0)
        checks.update({
            "attribute compiler matches its authenticated implementation": (
                authenticated_compiler_counter_contract(scanner_counts, bulk_compiler_profile(rom_bytes))
                and scanner_counts.get("compiler_d400_1a", 0)
                == scanner_counts.get("compiler_row_calls", -1)
                and scanner_counts.get("compiler_d400_f0", -1) == 0
                and scanner_counts.get("compiler_d400_other", -1) == 0
                and scanner_counts.get("compiler_orphan_rows", -1) == 0
                and scanner_counts.get("compiler_incomplete", -1) == 0
            ),
            "atomic copier receives an exact physical BG-map destination": (
                scanner_counts.get("atomic_setup", 0) > 0
                and scanner_counts.get("atomic_setup_invalid_h", -1) == 0
            ),
            "map-done consumes only exact even/odd destination tags": (
                pure_copies + dirty_copies > 0
                and scanner_counts.get("mapdone_invalid_latch", -1) == 0
                and scanner_counts.get("mapdone_even", -1) == pure_copies
                and scanner_counts.get("mapdone_odd", -1) == dirty_copies
            ),
            "expected planes promote only after exact dirty publications": (
                scanner_counts.get("expected_plane_promotions", -1)
                == scanner_counts.get("compiler_publications", -2)
                == dirty_copies
                and scanner_counts.get(
                    "expected_plane_invalid_promotions", -1
                ) == 0
                and scanner_counts.get("expected_plane_pending", -1) == 0
            ),
            "every completed hazard publication reaches its dispatcher": (
                publications > 0 and dispatches == publications
            ),
            "every dispatched hazard publication reaches its authenticated route": (
                publication_routes_exact(scanner_counts, publication_route_profile(rom_bytes))
            ),
            "hazard publications reach the semantic row writer": (
                semantic_writes >= scanner_entries > 0
            ),
        })
        if args.require_scene0b_low_health:
            scene0b_publications = scanner_counts.get("scene0b_postcopy", 0)
            scene0b_dispatches = scanner_counts.get("scene0b_dispatch", 0)
            scene0b_scanner_entries = scanner_counts.get("scene0b_front", 0)
            scene0b_semantic_writes = scanner_counts.get("scene0b_write", 0)
            scene0b_dirty_decisions = scanner_counts.get(
                "scene0b_decider_dirty", 0
            )
            scene0b_atomic_setups = scanner_counts.get(
                "scene0b_atomic_setup", 0
            )
            scene0b_dirty_copies = scanner_counts.get(
                "scene0b_dirty_copy", 0
            )
            checks.update({
                "scene-$0B uses the authenticated attribute compiler": (
                    authenticated_compiler_counter_contract(
                        scanner_counts, bulk_compiler_profile(rom_bytes), prefix="scene0b_"
                    )
                ),
                "scene-$0B reaches the Stage-1 split-key consumer": (
                    scanner_counts.get("runtime_gateway_scene0b", 0) > 0
                    and scanner_counts.get("split_consumer_scene0b", 0) > 0
                    and scanner_counts.get("runtime_entry_mismatches", 1) == 0
                    and scanner_counts.get(
                        "runtime_scene0b_entry_mismatches", 1
                    ) == 0
                ),
                "scene-$0B publications reach the hazard dispatcher": (
                    scene0b_publications > 0
                    and scene0b_dispatches == scene0b_publications
                ),
                "scene-$0B publications enter the geometry scanner": (
                    scanner_counts.get("scene0b_pure_helper", 0)
                    == scene0b_dispatches
                    and scene0b_scanner_entries == scene0b_dispatches
                ),
                "scene-$0B reaches the semantic row writer": (
                    scene0b_semantic_writes >= scene0b_scanner_entries > 0
                ),
                "scene-$0B dirty decision preserves physical destination H": (
                    scene0b_dirty_decisions > 0
                    and scene0b_atomic_setups == scene0b_dirty_decisions
                    and scanner_counts.get(
                        "scene0b_atomic_setup_invalid_h", -1
                    ) == 0
                ),
                "scene-$0B dirty decision reaches exact tagged map-done": (
                    scene0b_dirty_copies == scene0b_atomic_setups
                    and scanner_counts.get(
                        "scene0b_mapdone_odd", -1
                    ) == scene0b_dirty_copies
                    and scanner_counts.get(
                        "scene0b_mapdone_invalid_latch", -1
                    ) == 0
                ),
            })
    receipt = {
        "rom": str(args.rom.resolve()),
        "rom_sha256": digest(args.rom),
        "state": str(args.state.resolve()),
        "state_sha256": digest(args.state),
        "fixture_attr_normalization": fixture_attr_normalization,
        "observed_owner_address": f"{owner_address(rom_bytes):04X}",
        "live_fixture_tooth_only_rebind": fixture_tooth_rebind,
        "settle_frames": args.settle,
        "settle_input_mask": args.settle_keys,
        "settle_drive_frames": args.settle_drive_frames,
        "pre_trigger_frames": args.pre_trigger,
        "scene0b_profile_required": args.require_scene0b_low_health,
        "scene0b_stimulus_frames": args.scene0b_frames,
        "post_trigger_input_mask": args.post_trigger_keys,
        "recovery_drive_frames": args.recovery_drive_frames,
        "music_transition_required": args.require_music_transition,
        "pulse_countdown_required": args.require_pulse_countdown,
        "hazard_attributes_required": args.require_hazard_attributes,
        "hazard_publication_owner_required": (
            args.require_hazard_publication_owner
        ),
        "hazard_publication_counters": scanner_counts,
        "candidate_runtime": {
            "source_offsets": [
                f"0x{offset:X}" for offset in STAGE1_RUNTIME_SOURCE_OFFSETS
            ],
            "source_sha256": [
                hashlib.sha256(image).hexdigest()
                for image in runtime_images
            ],
            "matched_source": runtime_source,
            "mismatches": runtime_mismatches,
            "actual_sha256": (
                hashlib.sha256(runtime_actual).hexdigest()
                if len(runtime_actual) == STAGE1_RUNTIME_LENGTH else None
            ),
            "bound": runtime_bound,
        },
        "independent_semantic_oracle": {
            "stage1_lut_offset": f"0x{STAGE1_LUT_OFFSET:X}",
            "stage1_lut_sha256": canonical_stage1_lut_sha256,
            "reviewed_sha256": canonical_stage1_lut_sha256,
            "room01_runtime_wall_override": {
                "tiles": ["24", "27", "30", "33"],
                "attribute": "06",
            },
            "candidate_lut_is_reviewed": True,
        },
        "music_transition_sample": music_transition_sample,
        "native_pulse_timer_range": {
            "minimum": min(pulse_values, default=0),
            "maximum": max(pulse_values, default=0),
        },
        "healthy_samples": len(pre_frames),
        "low_health_frames": len(low_frames),
        "scene0b_frames": len(scene0b_frames),
        "native_scene0b_transition": {
            "first_dd06_sample": first_dd06_sample,
            "first_scene0b_sample": first_scene0b_sample,
            "first_recovered_sample": first_recovered_sample,
        },
        "ffe5_room01_observation": ffe5_observation,
        "sample_frames": len(frames),
        "requested_sample_frames": args.samples,
        "publication_completion_extra_frames": len(frames) - args.samples,
        "dma_unreadable_samples": len(dma_unreadable),
        "compiler_unreadable_samples": len(compiler_unreadable),
        "readable_samples": len(readable_frames),
        "bgp_writes_total": len(sampled_writes),
        "non_e4_bgp_writes": bad_writes[:32],
        "bg_cram_variants": len(cram_values),
        "visible_attr_layout_variants": {
            map_name: len(layouts)
            for map_name, layouts in sorted(attr_layouts.items())
        },
        "publication_owned_oracle": {
            "maps": sorted(publication_owner_maps),
            "missing_frames": len(publication_owner_missing_frames),
            "first_missing": (
                {
                    "sample": int(publication_owner_missing_frames[0]["sample"]),
                    "frame": int(publication_owner_missing_frames[0]["frame"]),
                    "map": publication_owner_missing_frames[0]["map"],
                }
                if publication_owner_missing_frames else None
            ),
            "room_register_only_handoffs": room_register_handoffs,
        },
        "maximum_transitional_lut_mismatches": max(
            int(row["mismatches"]) for row in readable_frames
        ),
        "maximum_unexpected_lut_mismatches": max(
            int(row["unexpected_mismatches"])
            for row in readable_frames
        ),
        "hazard_mismatch_frames": {
            "total": len(hazard_mismatch_frames),
            "pre_stimulus": sum(
                row.get("stimulus_phase") == "pre"
                for row in hazard_mismatch_frames
            ),
            "scene0b_stimulus": sum(
                row.get("stimulus_phase") == "scene0b"
                for row in hazard_mismatch_frames
            ),
            "recovered": sum(
                row.get("stimulus_phase") == "recovered"
                for row in hazard_mismatch_frames
            ),
            "healthy": sum(
                row["health_phase"] == "pre"
                for row in hazard_mismatch_frames
            ),
            "low_health": sum(
                row["health_phase"] == "low"
                for row in hazard_mismatch_frames
            ),
            "warning_music_scene": sum(
                row["d880"] == "0A" for row in hazard_mismatch_frames
            ),
            "first": (
                {
                    "sample": int(hazard_mismatch_frames[0]["sample"]),
                    "frame": int(hazard_mismatch_frames[0]["frame"]),
                    "health_phase": hazard_mismatch_frames[0]["health_phase"],
                    "stimulus_phase": hazard_mismatch_frames[0].get(
                        "stimulus_phase"
                    ),
                    "scene": hazard_mismatch_frames[0]["d880"],
                    "details": hazard_mismatch_frames[0]["mismatch_details"],
                }
                if hazard_mismatch_frames else None
            ),
        },
        "approved_colored_tooth_cells_visible": {
            "minimum": min(
                int(row["approved_bank1"]) for row in readable_frames
            ),
            "maximum": max(
                int(row["approved_bank1"]) for row in readable_frames
            ),
        },
        "render_metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
    }
    receipt_path = args.output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("FAIL: " + "; ".join(failed))
        print(f"Receipt: {receipt_path}")
        return 1
    print(
        f"PASS: crossed the warning threshold after {args.pre_trigger} healthy "
        f"frames and captured {len(low_frames)} low-health "
        "frames; BGP stayed E4, BG CRAM/attributes stayed stable, and no "
        "background-flash discontinuity rendered."
    )
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
