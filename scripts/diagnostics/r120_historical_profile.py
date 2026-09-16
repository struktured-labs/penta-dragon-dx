"""Exact historical r120 profile for a freshly generated production image.

This is an experimental reconstruction adapter, never a production default.
It reverses later integrated changes before the audited r120 -> r534 replay
reapplies its own exact lineage. Every modern preimage and the complete input
and output identities are checked. No retained ROM is read.
"""
from __future__ import annotations

import hashlib

import build_stage1_live_key_demo_dirty_r194 as attract
import build_stage1_menu_hidden_repair_r264 as menu_close
import build_stage1_r74_semantic_key_r190 as key
import build_stage1_phase_content_key_r208 as phase
import build_stage7_menu_signature_invalidation_r265 as menu_signature
import build_stage1_deferred_palette_r210 as handoff_history
import stage_card_palette_handoff as handoff
import build_v302_title_fix as production

FACTORY_SHA256 = "e5601c68ee050ae2fadf67cef5da6d04baae90cbe75ea2ea52964e5151924c90"
BASELINE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"

# Source-owned historical fragments not exposed as variants by current
# emitters. Each tuple names the operation, exact locations, current preimage,
# and r120 recipe. These are bounded instructions/tile rows, not a ROM image.
FRAGMENTS = (
    ("native menu selector reads DC0B", (0x200E,), "f040cb5f", "fa0bdca7"),
    ("historical tooth top art", (0x1D681,),
     "7fe73dff18ff55ff80ffd4ffe0fff0c3fee7fcff98ff55ff00ff15ff03ff07",
     "7ee73cff18ff00ff00ff00ff00ff00c37ee73cff18ff00ff00ff00ff00ff00"),
    ("historical tooth middle art", (0x1D767,),
     "7fe7bce7fcfff8fff0", "7ee73ce73cff18ff00"),
    ("historical tooth lower art", (0x1D775,),
     "fec37fe73ce73dff1bff07c37fc37fe73ce77dff98ffd4ffe0fff0c3fec3fee7bce77dff18ff15ff03ff07",
     "7ec37ee73ce73cff18ff00c37ec37ee73ce73cff18ff00ff00ff00c37ec37ee73ce73cff18ff00ff00ff00"),
    ("historical hazard BG7 black slot", (0x368CE, 0x428CE), "4a3d", "0000"),
    ("physical page compares H against 9C", (0x36A01, 0x42A01),
     "cb5428021e57cd137cc33d7d00", "7cfe9c20021e57cd137cc33d7d"),
    ("cold entry clears historical HRAM owners", (0x36C31, 0x42C31),
     "91772ea422772eb022773e05", "8b772e91772ea422772eab77"),
    ("historical story BG sweep starts at zero", (0x36D7A, 0x42D7A), "80", "00"),
    ("room entry clears B0/B1 before scroll restore", (0x36E71, 0x42E71),
     "8b772eab77e0913effea0ddfc30a56", "b02277e0913effea0ddfc30a560000"),
    ("terminal caps retain support palette 6", (0x3706B, 0x3706F, 0x3707B, 0x3707F,
                                               0x4306B, 0x4306F, 0x4307B, 0x4307F,
                                               0x5016B, 0x5016F, 0x5017B, 0x5017F,
                                               0x5046B, 0x5046F, 0x5047B, 0x5047F), "05", "06"),
    ("room03 scanner guard and saved-register leaf", (0x4EB70,),
     "000000000000000102030000000000000000000000", "cb582806c3b761010203f0bdfe03c2b761c1d1c5c9"),
    ("room03 scanner calls guarded leaf", (0x4EBE8,), "b761", "706b"),
    ("historical neutral tooth template", (0x4EC31,),
     "e0ffd4ff80ff55ff00ff15ff03ff07ff03ff15ff00ff55ff80ffd4ffe0fff0",
     "00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00"),
)


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def build(factory: bytes) -> tuple[bytes, dict]:
    if digest(factory) != FACTORY_SHA256:
        raise ValueError("r120 profile requires the exact freshly generated factory identity")
    result = bytearray(factory)
    records = []
    touched = set()

    def replace(name: str, offsets: tuple[int, ...], current: bytes, historical: bytes):
        if len(current) != len(historical) or not current:
            raise ValueError(f"{name}: fragment width changed")
        for offset in offsets:
            region = set(range(offset, offset + len(current)))
            if offset < 0x150 or offset + len(current) > len(result) or touched & region:
                raise ValueError(f"{name}: invalid or overlapping fragment range")
            if result[offset:offset + len(current)] != current:
                raise ValueError(f"{name}: modern preimage differs at {offset:#x}")
            touched.update(region)
            result[offset:offset + len(current)] = historical
        records.append({"name": name, "offsets": list(offsets), "length": len(current),
                        "modern_sha256": digest(current), "historical_sha256": digest(historical)})

    replace("r194 attract trampoline", (attract.TRAMPOLINE_OFFSET,),
            attract.NEW_TRAMPOLINE, attract.OLD_TRAMPOLINE)
    replace("r264 menu-close tail", (menu_close.MENU_CLOSE_TAIL,),
            menu_close.NATIVE_HIDDEN_HANDOFF, menu_close.FORCED_VISIBLE_REPAIR)
    replace("pre-r190 semantic runtime", key.RUNTIME_OFFSETS, phase.NEW_RUNTIME, key.R120_RUNTIME)
    modern_menu = production.build_stale_window_cleanup(buffered_stage1_attrs=True)
    replace("Stage-1-only Window signature helper", (0x36A40,),
            modern_menu, menu_signature.OLD_HELPER)
    replace("pre-r210 entry palette arm", (handoff.STAGE1_ENTRY_GATE_OFFSET,),
            handoff.DEFERRED_ENTRY_GATE, handoff_history.OLD_ENTRY_GATE)
    bg0 = factory[handoff.STAGE1_BG0_OFFSET:handoff.STAGE1_BG0_OFFSET + 8]
    title = factory[handoff.TITLE_BG0_OFFSET:handoff.TITLE_BG0_OFFSET + 8]
    index = handoff._choose_discriminator(bg0, title)
    modern = handoff._build_private_helper(bg0, index, title[index], arm_palette_phase=True)
    legacy = handoff._build_private_helper(bg0, index, title[index], arm_palette_phase=False)
    if len(modern) != len(legacy) + 5:
        raise ValueError("historical handoff phase-arm width changed")
    replace("pre-r210 Stage-card private helper", (handoff.PRIVATE_OFFSET,),
            modern, legacy + bytes([0xFF]) * 5)
    for name, offsets, current, historical in FRAGMENTS:
        replace(name, offsets, bytes.fromhex(current), bytes.fromhex(historical))
    checksum = (sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF
    result[0x14E:0x150] = checksum.to_bytes(2, "big")
    candidate = bytes(result)
    if digest(candidate) != BASELINE_SHA256:
        raise ValueError("historical source profile did not reproduce exact r120")
    changed = {i for i, (a, b) in enumerate(zip(factory, candidate)) if a != b}
    if changed - touched - {0x14E, 0x14F}:
        raise ValueError("r120 reconstruction escaped declared source fragments")
    return candidate, {
        "schema": "penta-r120-historical-source-profile-v1",
        "experimental": True, "promotable": False,
        "factory_sha256": digest(factory), "candidate_sha256": digest(candidate),
        "retained_roms_read": False, "fresh_live_qualification": False,
        "changed_bytes": len(changed), "fragments": records,
    }
