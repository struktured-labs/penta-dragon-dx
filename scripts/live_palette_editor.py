#!/usr/bin/env python3
"""Live palette editor — browser-based GUI for tuning Penta Dragon DX CGB colors.

Workflow:
  1. Start the guarded emulator/editor pair:
       scripts/palette_session.sh start
  2. Open http://localhost:8077 in a browser.
  3. Adjust colors. Emulator-side CRAM changes appear within ~0.5s.

Live adjustment is intentionally a development/streaming tool. It does not
modify the running ROM. "Save to YAML" followed by a deterministic rebuild is
the separate path for making an audience-selected palette ship in the patch.

The browser saves color picks to rom/working/live_palettes.txt. The mGBA Lua
script polls that file every 30 frames (~0.5s) and rewrites CGB palette
CRAM (BCPS/BCPD for BG, OCPS/OCPD for OBJ) with the new values.

To persist tuned colors, click "Save to YAML". The editor updates only the
palette color arrays in palettes/penta_palettes_v097.yaml and preserves its
comments and structure.

Color format in rom/working/live_palettes.txt:
  BG<n>:<idx>=<hex>,<idx>=<hex>,...
  OBJ<n>:<idx>=<hex>,<idx>=<hex>,...
where <hex> is 4-char BGR555 (e.g. "7FFF") or 6-char RGB hex.

Default palettes are loaded from palettes/penta_palettes_v097.yaml.
"""
import http.server
import argparse
import hashlib
import json
import os
import socketserver
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    print("Install: pip install pyyaml")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
LIVE_FILE = Path(os.environ.get(
    "PENTA_LIVE_PALETTE_FILE",
    ROOT / "rom" / "working" / "live_palettes.txt",
))
YAML_PATH = Path(os.environ.get(
    "PENTA_PALETTE_YAML",
    ROOT / "palettes" / "penta_palettes_v097.yaml",
))
YAML_BACKUP_DIR = Path(os.environ.get(
    "PENTA_PALETTE_BACKUP_DIR",
    ROOT / "tmp" / "palette_session" / "backups",
))

PORT = 8077

# Release-safe navigation presets. mGBA loads these emulator states directly;
# no ROM memory/stack redirect or SELECT+START teleport is involved.
SCENE_PRESETS = [
    ("title", "Title / idle reel", "title_screen.ss0"),
    (
        "opening",
        "Story intro — first text (default title option)",
        "generated-story:opening.ss0",
    ),
    (
        "opening_book",
        "Story intro — magic book (BG1)",
        "generated-story:opening_book.ss0",
    ),
    (
        "opening_sara",
        "Story intro — Sara (BG2)",
        "generated-story:opening_sara.ss0",
    ),
    (
        "opening_dragon_eye",
        "Story intro — dragon eye (BG3)",
        "generated-story:opening_dragon_eye.ss0",
    ),
    (
        "pre_final_story",
        "Pre-final story — Penta Dragon (BG4)",
        "generated-story:pre_final.ss0",
    ),
    (
        "pre_final_sara",
        "Pre-final story — Sara (BG7)",
        "generated-story:pre_final_sara.ss0",
    ),
    (
        "post_final_story",
        "Post-final story — dragon (BG5)",
        "generated-story:post_final.ss0",
    ),
    (
        "post_final_lisa",
        "Post-final story — Lisa (BG6)",
        "generated-story:post_final_lisa.ss0",
    ),
    (
        "post_final_sara",
        "Post-final story — Sara (BG7)",
        "generated-story:post_final_sara.ss0",
    ),
    (
        "ending_credits",
        "Ending — credits (BG1)",
        "generated-story:ending_credits.ss0",
    ),
    (
        "ending_end",
        "Ending — END page (BG2)",
        "generated-story:ending_end.ss0",
    ),
    (
        "ending_epilogue",
        "Ending — epilogue text (BG3)",
        "generated-story:ending_epilogue.ss0",
    ),
    ("stage2", "Stage 2", "generated:stage2.ss0"),
    ("stage3", "Stage 3", "generated:stage3.ss0"),
    ("stage4", "Stage 4", "generated:stage4.ss0"),
    ("stage5", "Stage 5 lava", "generated:stage5.ss0"),
    ("stage6", "Stage 6", "generated:stage6.ss0"),
    ("stage7", "Stage 7 lava", "generated:stage7.ss0"),
    ("boss_shalamar", "Boss 1 — Shalamar", "generated-boss:boss0_shalamar.ss0"),
    ("boss_riff", "Boss 2 — Riff", "generated-boss:boss1_riff.ss0"),
    (
        "boss_crystal_dragon",
        "Boss 3 — Crystal Dragon",
        "generated-boss:boss2_crystal_dragon.ss0",
    ),
    ("boss_cameo", "Boss 4 — Cameo", "generated-boss:boss3_cameo.ss0"),
    ("boss_ted", "Boss 5 — Ted", "generated-boss:boss4_ted.ss0"),
    ("boss_troop", "Boss 6 — Troop", "generated-boss:boss5_troop.ss0"),
    ("boss_faze", "Boss 7 — Faze", "generated-boss:boss6_faze.ss0"),
    ("boss_angela", "Boss 8 — Angela", "generated-boss:boss7_angela.ss0"),
    (
        "boss_penta_dragon",
        "Final Boss — Penta Dragon",
        "generated-boss:boss8_penta_dragon.ss0",
    ),
    ("witch", "Sara Witch", "level1_sara_w_alone.ss0"),
    ("dragon", "Sara Dragon", "level1_sara_d_alone.ss0"),
    ("crow", "Crow", "level1_sara_w_crow.ss0"),
    ("hornets", "Four hornets", "level1_sara_w_4_hornets.ss0"),
    ("orc", "Orc", "level1_sara_w_orc.ss0"),
    ("soldier", "Soldier", "level1_sara_w_soldier.ss0"),
    ("mage", "Mage + items", "level1_sara_w_mage_health1_items.ss0"),
    (
        "mixed",
        "Catfish / moth / hazards",
        "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    ),
    ("gargoyle", "Gargoyle miniboss", "level1_sara_w_gargoyle_mini_boss.ss0"),
    ("spider", "Spider miniboss", "level1_sara_w_spier_miniboss.ss0"),
    (
        "spiral",
        "Spiral projectile (FFC0=1)",
        "sara_d_special_spiral_weapon_activated_level1_v_2.31.ss0",
    ),
    (
        "shield",
        "Shield projectile (FFC0=2)",
        "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    ),
    ("jet", "Secret jet stage", "level1_sara_w_in_jet_form_secret_stage.ss0"),
    ("menu", "Item menu", "level1_square_cat_fish_menu_open.ss0"),
]
SCENE_KEYS = {key for key, _label, _state in SCENE_PRESETS}
STATE_LOCK = threading.RLock()
SCENE_REQUEST_ID = 0

# Per-stage-boss BG palette assignments — mirrors the _bg_table_<boss>()
# functions in scripts/build_v301_teleport.py. Each boss's body tiles map
# to a set of BG palette indices; the indices below are the ones the
# user actually sees on screen when that boss's arena is loaded (via
# the per-arena bg_table swapped into WRAM 0xDA00 by scene_detect).
#
# Editing the listed BG palette's colors live tunes that body region on
# the named boss. Palette CRAM is shared globally, so changing BG3 also
# affects every other boss whose body uses BG3 — for true per-arena
# CRAM, the build pipeline would need per-arena palette tables (next
# phase). The "body part" labels below are guidance for tuning intent.
STAGE_BOSS_BODY_PALETTES = [
    # (FFBA, name, [(BG pal idx, body part label), ...])
    # Labels reflect ACTUAL CRAM colors per BG palette index:
    #   BG1 gold, BG2 purple, BG3 green, BG4 ice cyan,
    #   BG5 fire (yellow/orange/red), BG6 stone gray, BG7 navy blue.
    (0, "Shalamar (Stage 1)", [
        (4, "head crest (ice)"), (6, "shell (stone)"),
        (5, "upper claws (fire)"), (3, "lower claws (green)"),
    ]),
    (1, "Riff (Stage 2)", [
        (5, "skull (fire)"), (1, "body (gold)"), (6, "limbs (stone)"),
    ]),
    (2, "Crystal Dragon (Stage 3)", [
        (4, "dome (ice)"), (7, "body (navy)"), (1, "sparkle core (gold)"),
    ]),
    (3, "Cameo (Stage 4)", [
        (2, "crown (purple)"), (6, "face (stone)"), (1, "ribbon (gold)"),
    ]),
    (4, "Ted (Stage 5)", [
        (5, "eyes (fire)"), (6, "body (stone)"), (7, "tendrils (navy)"),
    ]),
    (5, "Troop (Stage 6)", [
        (2, "heads (purple)"), (6, "body (stone)"), (1, "glow (gold)"),
    ]),
    (6, "Faze (Stage 7)", [
        (4, "horns (ice)"), (5, "body (fire)"),
        (2, "torso (purple)"), (7, "accents (navy)"),
    ]),
    (7, "Angela", [
        (6, "head (stone)"), (2, "body (purple)"), (4, "tentacles (ice)"),
    ]),
    (8, "Penta Dragon (Final)", [
        (4, "heads (ice)"), (1, "body/wings (gold)"),
        (5, "banner (fire)"), (7, "base (navy)"),
    ]),
]


# Boss-palette YAML entries (FFBF 1-8 → boss-palette CRAM override).
# These are SEPARATE from stage-boss arena identification. They are
# the entries that v3.01's palette_loader writes when FFBF != 0
# (replacing the OBJ slot from the boss_slot_table). The names below
# are the YAML keys. FFBF 1/2 are verified Gargoyle/Spider minibosses;
# the legacy names for 3-8 remain builder-facing identifiers.
BOSS_PAL_ENTRIES = [
    # (FFBF value, YAML key, OBJ slot from boss_slot_table)
    (1, "Gargoyle",       6),
    (2, "Spider",         7),
    (3, "Boss3_Crimson",  6),
    (4, "Boss4_Ice",      7),
    (5, "Boss5_Void",     6),
    (6, "Boss6_Poison",   7),
    (7, "Boss7_Knight",   4),
    (8, "Angela",         5),
]

JET_PAL_ENTRIES = [
    # (OBJ slot, YAML key)
    (1, "SaraDragonJet"),
    (2, "SaraWitchJet"),
]

POWERUP_PAL_ENTRIES = [
    # (FFC0 value, YAML key)
    (1, "SpiralProjectile"),
    (2, "ShieldProjectile"),
    (3, "TurboProjectile"),
]


def bgr555_to_rgb888(val15: int) -> str:
    r5 = val15 & 0x1F
    g5 = (val15 >> 5) & 0x1F
    b5 = (val15 >> 10) & 0x1F
    r = (r5 * 255 + 15) // 31
    g = (g5 * 255 + 15) // 31
    b = (b5 * 255 + 15) // 31
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb888_to_bgr555(rgb_hex: str) -> int:
    s = rgb_hex.lstrip("#")
    r = int(s[0:2], 16) if len(s) >= 6 else 0
    g = int(s[2:4], 16) if len(s) >= 6 else 0
    b = int(s[4:6], 16) if len(s) >= 6 else 0
    r5 = min(31, (r * 31 + 127) // 255)
    g5 = min(31, (g * 31 + 127) // 255)
    b5 = min(31, (b * 31 + 127) // 255)
    return (b5 << 10) | (g5 << 5) | r5


def load_yaml_palettes() -> dict:
    """Returns {kind: {pal_idx: [color_hex × 4]}}."""
    with open(YAML_PATH) as f:
        data = yaml.safe_load(f)
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    obj_keys = ['EnemyProjectile', 'SaraDragon', 'SaraWitch',
                'SaraProjectileAndCrow', 'Hornets', 'OrcGround',
                'Humanoid', 'Catfish']
    palettes = {"BG": {}, "OBJ": {}, "BOSS": {}, "JET": {}, "POWER": {}}
    for i, k in enumerate(bg_keys):
        entry = data.get('bg_palettes', {}).get(k, {})
        palettes["BG"][i] = entry.get('colors', ["7FFF", "5294", "2108", "0000"])
    for i, k in enumerate(obj_keys):
        entry = data.get('obj_palettes', {}).get(k, {})
        palettes["OBJ"][i] = entry.get('colors', ["0000", "7C1F", "4C0F", "0000"])
    # Boss-palette override entries from YAML.
    for ffbf, yaml_key, _slot in BOSS_PAL_ENTRIES:
        entry = data.get('boss_palettes', {}).get(yaml_key, {})
        palettes["BOSS"][ffbf] = entry.get('colors', ["0000", "7C1F", "4C0F", "0000"])
    for slot, yaml_key in JET_PAL_ENTRIES:
        entry = data.get('obj_palettes', {}).get(yaml_key, {})
        palettes["JET"][slot] = entry.get(
            'colors', ["0000", "7FE0", "4EC0", "2D80"]
        )
    for power, yaml_key in POWERUP_PAL_ENTRIES:
        entry = data.get('powerup_palettes', {}).get(yaml_key, {})
        palettes["POWER"][power] = entry.get(
            'colors', ["0000", "03FF", "02BF", "019F"]
        )
    palettes["BG_labels"] = bg_keys
    palettes["OBJ_labels"] = obj_keys
    return palettes


def write_live_file(
    state: dict,
    dirty: dict[str, set[int]],
    *,
    scene: str | None = None,
    scene_request_id: int | None = None,
) -> None:
    """Write the current state dict to LIVE_FILE in mGBA-readable format.

    Only explicitly edited base or guarded special palettes are emitted. This
    lets a live edit survive the game's own palette reloads without
    overwriting unrelated boss or scene-specific CRAM. `scene` is a one-shot,
    whitelisted mGBA save-state load request; it never changes ROM control
    flow. Its monotonically increasing request ID makes repeated clicks on the
    same scene produce different bridge bytes so mGBA cannot mistake them for
    an old request.
    """
    with STATE_LOCK:
        lines = ["# Auto-generated by live_palette_editor.py"]
        for kind in ("BG", "OBJ"):
            for pal_idx in sorted(dirty[kind]):
                colors = state[kind][pal_idx]
                entries = ",".join(
                    f"{ci}={c.upper()}" for ci, c in enumerate(colors)
                )
                lines.append(f"{kind}{pal_idx}:{entries}")
        for ffbf in sorted(dirty["BOSS"]):
            colors = state["BOSS"][ffbf]
            slot = next(
                slot
                for entry_ffbf, _key, slot in BOSS_PAL_ENTRIES
                if entry_ffbf == ffbf
            )
            entries = ",".join(
                f"{ci}={color.upper()}"
                for ci, color in enumerate(colors)
            )
            lines.append(f"BOSS{ffbf}@{slot}:{entries}")
        for slot in sorted(dirty["JET"]):
            colors = state["JET"][slot]
            entries = ",".join(
                f"{ci}={color.upper()}"
                for ci, color in enumerate(colors)
            )
            lines.append(f"JET{slot}:{entries}")
        for power in sorted(dirty["POWER"]):
            colors = state["POWER"][power]
            entries = ",".join(
                f"{ci}={color.upper()}"
                for ci, color in enumerate(colors)
            )
            lines.append(f"POWER{power}:{entries}")
        if scene is not None:
            if scene not in SCENE_KEYS:
                raise ValueError(f"unknown scene preset: {scene}")
            if scene_request_id is None:
                raise ValueError("scene request ID is required")
            lines.append(f"# SCENE_REQUEST:{scene_request_id}")
            lines.append(f"SCENE:{scene}")
        LIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = LIVE_FILE.with_suffix(LIVE_FILE.suffix + ".tmp")
        temporary.write_text("\n".join(lines) + "\n")
        temporary.replace(LIVE_FILE)


# Global state
STATE = load_yaml_palettes()
DIRTY: dict[str, set[int]] = {
    "BG": set(),
    "OBJ": set(),
    "BOSS": set(),
    "JET": set(),
    "POWER": set(),
}
write_live_file(STATE, DIRTY)


def render_index():
    """Generate HTML page with palette pickers."""
    html_parts = ["""<!DOCTYPE html>
<html><head><title>Penta Dragon DX Live Palette</title>
<style>
body { font-family: sans-serif; background: #1a1a1a; color: #eee; padding: 1em; }
h1 { margin: 0 0 0.5em 0; }
.section { margin-bottom: 1.5em; }
.pal { display: inline-block; margin: 0.5em 1em 0.5em 0; vertical-align: top; }
.pal-name { font-size: 0.9em; margin-bottom: 0.3em; color: #aaa; }
.color { display: inline-block; width: 32px; height: 32px; margin: 0 2px;
         border: 1px solid #555; cursor: pointer; }
.color-row { display: flex; }
input[type=color] { width: 32px; height: 32px; padding: 0; border: 0;
                    background: transparent; cursor: pointer; }
button { padding: 0.5em 1em; margin: 0.3em; background: #444;
         color: #eee; border: 1px solid #666; cursor: pointer; }
button:hover { background: #666; }
.preset { display: inline-block; padding: 0.3em 0.5em;
          background: #2a4; color: white; cursor: pointer; margin-right: 0.3em; }
.bgr { font-family: monospace; font-size: 0.75em; color: #888;
       margin-top: 0.2em; min-width: 32px; display: inline-block; }
</style></head><body>
<h1>Penta Dragon DX — Live Palette Editor</h1>
<p>Edits apply to running mGBA within ~0.5s.
Make sure mGBA was launched with <code>--script scripts/lua/live_palettes.lua</code>.</p>
<button onclick="reload()">Reset live colors from YAML</button>
<button onclick="save()">Save to YAML</button>
<button onclick="copyState()">Copy current as JSON</button>
"""]

    # Release-safe scene navigation. These buttons load curated emulator states;
    # they do not patch game memory or invoke the retired in-ROM teleport.
    html_parts.append('<div class="section"><h2>Stream Scene Deck</h2>')
    html_parts.append('<p style="font-size:0.85em;color:#aaa;">'
                      'Jump between representative actors and screens by loading '
                      'curated mGBA states. This is emulator-only navigation on '
                      '<code>FIXED.gb</code>; it cannot trigger the retired '
                      'SELECT+START stack redirect.</p>')
    html_parts.append('<p style="font-size:0.85em;color:#aaa;">'
                      'The first title option is the story intro; DOWN selects '
                      'the actual GAME START option. Story-art buttons marked '
                      'BG1–BG7 preview that palette on the artwork only. The '
                      'separator, dialogue border, and text stay on neutral BG0.'
                      ' Credits, END, and epilogue buttons use independent '
                      'ending-phase guards and preview BG1, BG2, and BG3.'
                      '</p>')
    html_parts.append('<div style="display:flex;flex-wrap:wrap;gap:0.3em;">')
    for key, label, _state in SCENE_PRESETS:
        html_parts.append(
            f'<button onclick="loadScene(\'{key}\')">{label}</button>'
        )
    html_parts.append("</div></div>")

    # ─── Per-stage-boss body palette editor ───
    # Shows the BG palette indices each boss's bg_table assigns to body
    # regions (mirrors _bg_table_<boss>() in build_v301_teleport.py).
    # Editing the colors here writes selected overrides to live CRAM.
    html_parts.append('<div class="section"><h2>Stage Boss Body Palettes</h2>')
    html_parts.append('<p style="font-size:0.85em;color:#888;">'
                      'Each boss\'s body is drawn with a few BG palette indices (assigned by '
                      'the per-arena <code>bg_table</code> in bank 13, swapped into WRAM 0xDA00 '
                      'when D880 changes). Click a boss to expand and edit the palettes that '
                      'cover its body. <strong>Note:</strong> BG palette CRAM is shared across all '
                      'bosses, so editing pal 3 here also affects every other boss whose body uses '
                      'pal 3. Per-arena CRAM is a future phase.</p>')
    for ffba, name, parts in STAGE_BOSS_BODY_PALETTES:
        html_parts.append(f'<details style="margin:0.4em 0;border:1px solid #333;padding:0.4em;">')
        html_parts.append(f'<summary style="cursor:pointer;font-weight:bold;">{name} '
                          f'<span style="font-weight:normal;color:#aaa;">'
                          f'(uses BG ' + ', '.join(str(p) for p, _ in parts) + ')</span></summary>')
        for pal_idx, body_part in parts:
            colors = STATE["BG"].get(pal_idx, ["0000"] * 4)
            html_parts.append('<div class="pal" style="margin:0.3em 0;padding:0.3em;background:#1a1a1a;">')
            html_parts.append(f'<div class="pal-name">BG{pal_idx} — <em>{body_part}</em></div>')
            html_parts.append('<div class="color-row" style="margin-top:0.3em;">')
            for ci, c in enumerate(colors):
                val15 = int(c, 16)
                rgb = bgr555_to_rgb888(val15)
                html_parts.append(
                    f'<div><input type="color" value="{rgb}" '
                    f'data-kind="BG" data-pal="{pal_idx}" data-color="{ci}" '
                    f'onchange="updateColor(this)">'
                    f'<div class="bgr" id="bgr-BG-{pal_idx}-{ci}-boss{ffba}">{c.upper()}</div></div>'
                )
            html_parts.append("</div></div>")
        html_parts.append("</details>")
    html_parts.append("</div>")

    html_parts.append(
        '<div class="section"><h2>Miniboss / Boss Override Palettes</h2>'
    )
    html_parts.append(
        '<p style="font-size:0.85em;color:#888;">'
        'These are the exact YAML palettes loaded when <code>FFBF=1..8</code>. '
        'Each override is applied live only while its matching flag is active, '
        'then saved back to the same builder entry. FFBF 1 and 2 are the '
        'verified Gargoyle and Spider minibosses; 3–8 retain their legacy '
        'builder labels.</p>'
    )
    for ffbf, yaml_key, slot in BOSS_PAL_ENTRIES:
        colors = STATE["BOSS"][ffbf]
        html_parts.append(
            '<div class="pal">'
            f'<div class="pal-name">FFBF {ffbf}: {yaml_key} → OBJ{slot}</div>'
            '<div class="color-row">'
        )
        for color_index, color in enumerate(colors):
            rgb = bgr555_to_rgb888(int(color, 16))
            html_parts.append(
                f'<div><input type="color" value="{rgb}" '
                f'data-kind="BOSS" data-pal="{ffbf}" '
                f'data-color="{color_index}" onchange="updateColor(this)">'
                f'<div class="bgr" '
                f'id="bgr-BOSS-{ffbf}-{color_index}">'
                f'{color.upper()}</div></div>'
            )
        html_parts.append("</div></div>")
    html_parts.append("</div>")

    html_parts.append('<div class="section"><h2>Jet Form Palettes</h2>')
    html_parts.append(
        '<p style="font-size:0.85em;color:#888;">'
        'These replace Sara Dragon/Witch in the secret stage only while '
        '<code>FFD0=1</code>, and save directly to their alternate OBJ YAML '
        'entries.</p>'
    )
    for slot, yaml_key in JET_PAL_ENTRIES:
        colors = STATE["JET"][slot]
        html_parts.append(
            '<div class="pal">'
            f'<div class="pal-name">{yaml_key} → OBJ{slot}</div>'
            '<div class="color-row">'
        )
        for color_index, color in enumerate(colors):
            rgb = bgr555_to_rgb888(int(color, 16))
            html_parts.append(
                f'<div><input type="color" value="{rgb}" '
                f'data-kind="JET" data-pal="{slot}" '
                f'data-color="{color_index}" onchange="updateColor(this)">'
                f'<div class="bgr" id="bgr-JET-{slot}-{color_index}">'
                f'{color.upper()}</div></div>'
            )
        html_parts.append("</div></div>")
    html_parts.append("</div>")

    html_parts.append(
        '<div class="section"><h2>Powerup Projectile Palettes</h2>'
    )
    html_parts.append(
        '<p style="font-size:0.85em;color:#888;">'
        'These replace OBJ0 only while the exact <code>FFC0</code> powerup '
        'value is active. Spiral and Shield have curated scene buttons; Turbo '
        'remains builder-tunable even though no natural FFC0=3 state is '
        'currently available.</p>'
    )
    for power, yaml_key in POWERUP_PAL_ENTRIES:
        colors = STATE["POWER"][power]
        html_parts.append(
            '<div class="pal">'
            f'<div class="pal-name">FFC0 {power}: {yaml_key} → OBJ0</div>'
            '<div class="color-row">'
        )
        for color_index, color in enumerate(colors):
            rgb = bgr555_to_rgb888(int(color, 16))
            html_parts.append(
                f'<div><input type="color" value="{rgb}" '
                f'data-kind="POWER" data-pal="{power}" '
                f'data-color="{color_index}" onchange="updateColor(this)">'
                f'<div class="bgr" id="bgr-POWER-{power}-{color_index}">'
                f'{color.upper()}</div></div>'
            )
        html_parts.append("</div></div>")
    html_parts.append("</div>")

    for kind in ("BG", "OBJ"):
        labels = STATE.get(kind + "_labels", [f"{kind}{i}" for i in range(8)])
        html_parts.append(f'<div class="section"><h2>{kind} Palettes</h2>')
        for pal_idx in range(8):
            colors = STATE[kind].get(pal_idx, ["0000"] * 4)
            label = labels[pal_idx]
            html_parts.append(f'<div class="pal"><div class="pal-name">{kind}{pal_idx}: {label}</div><div class="color-row">')
            for ci, c in enumerate(colors):
                val15 = int(c, 16)
                rgb = bgr555_to_rgb888(val15)
                html_parts.append(
                    f'<div><input type="color" value="{rgb}" '
                    f'data-kind="{kind}" data-pal="{pal_idx}" data-color="{ci}" '
                    f'onchange="updateColor(this)">'
                    f'<div class="bgr" id="bgr-{kind}-{pal_idx}-{ci}">{c.upper()}</div></div>'
                )
            html_parts.append("</div></div>")
        html_parts.append("</div>")

    html_parts.append("""
<script>
function rgb888_to_bgr555(rgb) {
    const s = rgb.replace('#', '');
    const r = parseInt(s.substr(0, 2), 16);
    const g = parseInt(s.substr(2, 2), 16);
    const b = parseInt(s.substr(4, 2), 16);
    const r5 = Math.min(31, Math.round(r * 31 / 255));
    const g5 = Math.min(31, Math.round(g * 31 / 255));
    const b5 = Math.min(31, Math.round(b * 31 / 255));
    return ((b5 << 10) | (g5 << 5) | r5).toString(16).padStart(4, '0').toUpperCase();
}
function updateColor(input) {
    const kind = input.dataset.kind;
    const pal = parseInt(input.dataset.pal);
    const color = parseInt(input.dataset.color);
    const bgr = rgb888_to_bgr555(input.value);
    // Update hex labels in both the global section and any per-boss views
    // that include this same palette. Match the canonical ID plus any
    // `-boss<N>` suffixes introduced by the per-stage-boss editor.
    const idPrefix = `bgr-${kind}-${pal}-${color}`;
    document.querySelectorAll(`[id="${idPrefix}"], [id^="${idPrefix}-"]`).forEach(el => {
        el.textContent = bgr;
    });
    // Mirror the new color into every <input type="color"> sharing the same
    // kind/pal/color (per-boss view and global view stay in sync).
    document.querySelectorAll(
        `input[type="color"][data-kind="${kind}"][data-pal="${pal}"][data-color="${color}"]`
    ).forEach(el => { if (el !== input) el.value = input.value; });
    fetch('/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({kind, pal, color, bgr})
    });
}
function loadScene(scene) {
    fetch('/load_scene', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({scene})
    }).then(r => r.text()).then(t => console.log('load_scene:', t));
}
function reload() {
    fetch('/reload', {method: 'POST'}).then(() => location.reload());
}
function save() {
    fetch('/save', {method: 'POST'}).then(r => r.text()).then(t => alert(t));
}
function copyState() {
    fetch('/state').then(r => r.text()).then(t => {
        navigator.clipboard.writeText(t);
        alert("State copied to clipboard");
    });
}
</script>
</body></html>""")
    return "\n".join(html_parts)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence default logging

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/" or url.path == "/index.html":
            with STATE_LOCK:
                body = render_index().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/state":
            with STATE_LOCK:
                body = json.dumps(STATE, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global STATE, DIRTY, SCENE_REQUEST_ID
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        if url.path == "/update":
            try:
                data = json.loads(body)
                kind = data["kind"]
                pal = int(data["pal"])
                color = int(data["color"])
                bgr = data["bgr"].upper()
                if kind not in ("BG", "OBJ", "BOSS", "JET", "POWER"):
                    raise ValueError(
                        "kind must be BG, OBJ, BOSS, JET, or POWER, "
                        f"got {kind!r}"
                    )
                valid_palettes = {
                    "BG": range(8),
                    "OBJ": range(8),
                    "BOSS": range(1, 9),
                    "JET": range(1, 3),
                    "POWER": range(1, 4),
                }[kind]
                if pal not in valid_palettes:
                    expected = {
                        "BG": "0-7",
                        "OBJ": "0-7",
                        "BOSS": "1-8",
                        "JET": "1-2",
                        "POWER": "1-3",
                    }[kind]
                    raise ValueError(f"{kind} palette must be {expected}, got {pal}")
                if color not in range(4):
                    raise ValueError(f"color must be 0-3, got {color}")
                if not re.fullmatch(r"[0-7][0-9A-F]{3}", bgr):
                    raise ValueError(f"invalid BGR555 value: {bgr!r}")
                with STATE_LOCK:
                    STATE[kind][pal][color] = bgr
                    DIRTY[kind].add(pal)
                    write_live_file(STATE, DIRTY)
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/load_scene":
            try:
                data = json.loads(body)
                scene = str(data.get("scene", ""))
                if scene not in SCENE_KEYS:
                    raise ValueError(f"unknown scene preset: {scene!r}")
                with STATE_LOCK:
                    SCENE_REQUEST_ID += 1
                    write_live_file(
                        STATE,
                        DIRTY,
                        scene=scene,
                        scene_request_id=SCENE_REQUEST_ID,
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"scene load requested: {scene}".encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/reload":
            with STATE_LOCK:
                STATE = load_yaml_palettes()
                # Reset only palettes overridden during this session. Unrelated
                # scene/boss CRAM remains owned by the game.
                write_live_file(STATE, DIRTY)
            self.send_response(200)
            self.end_headers()
        elif url.path == "/save":
            try:
                with STATE_LOCK:
                    changed, backup = self.save_to_yaml()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                if changed:
                    message = f"Saved to {YAML_PATH}\nBackup: {backup}"
                else:
                    message = f"No palette changes; {YAML_PATH} is unchanged"
                self.wfile.write(message.encode())
            except Exception as error:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"error: {error}".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def save_to_yaml(self) -> tuple[bool, Path | None]:
        """Update only palette color arrays while preserving YAML commentary."""
        text = YAML_PATH.read_text()
        replacements: dict[tuple[str, str], list[str]] = {}
        for index, key in enumerate(STATE.get("BG_labels", [])):
            replacements[("bg_palettes", key)] = STATE["BG"][index]
        for index, key in enumerate(STATE.get("OBJ_labels", [])):
            replacements[("obj_palettes", key)] = STATE["OBJ"][index]
        for ffbf, yaml_key, _slot in BOSS_PAL_ENTRIES:
            replacements[("boss_palettes", yaml_key)] = STATE["BOSS"][ffbf]
        for slot, yaml_key in JET_PAL_ENTRIES:
            replacements[("obj_palettes", yaml_key)] = STATE["JET"][slot]
        for power, yaml_key in POWERUP_PAL_ENTRIES:
            replacements[("powerup_palettes", yaml_key)] = STATE["POWER"][power]

        lines = text.splitlines(keepends=True)
        section = None
        palette = None
        replaced: set[tuple[str, str]] = set()
        for index, line in enumerate(lines):
            section_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
            if section_match:
                section = section_match.group(1)
                palette = None
                continue
            palette_match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
            if palette_match:
                palette = palette_match.group(1)
                continue
            key = (section, palette)
            if key not in replacements:
                continue
            color_match = re.match(
                r'^(\s*colors:\s*)\[[^\]]*\](\s*(?:#.*)?)((?:\r?\n)?)$',
                line,
            )
            if not color_match:
                continue
            colors = ", ".join(f'"{value}"' for value in replacements[key])
            lines[index] = (
                f"{color_match.group(1)}[{colors}]"
                f"{color_match.group(2)}{color_match.group(3)}"
            )
            replaced.add(key)

        missing = set(replacements) - replaced
        if missing:
            names = ", ".join(f"{section}.{key}" for section, key in sorted(missing))
            raise RuntimeError(f"palette entries not found in YAML: {names}")

        updated = "".join(lines)
        original_bytes = text.encode()
        updated_bytes = updated.encode()
        if updated_bytes == original_bytes:
            return False, None

        digest = hashlib.md5(original_bytes).hexdigest()
        backup_name = (
            f"{YAML_PATH.stem}.presave_{digest[:8]}.backup{YAML_PATH.suffix}"
        )
        YAML_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = YAML_BACKUP_DIR / backup_name
        if backup.exists():
            if backup.read_bytes() != original_bytes:
                raise RuntimeError(f"refusing mismatched palette backup: {backup}")
        else:
            backup_tmp = backup.with_suffix(backup.suffix + ".tmp")
            backup_tmp.write_bytes(original_bytes)
            backup_tmp.replace(backup)

        temporary = YAML_PATH.with_suffix(YAML_PATH.suffix + ".tmp")
        temporary.write_bytes(updated_bytes)
        temporary.replace(YAML_PATH)
        return True, backup


class PaletteHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    print(f"Live palette editor")
    print(f"  Browser: http://{args.bind}:{args.port}")
    print(f"  mGBA Lua script: scripts/lua/live_palettes.lua")
    print(f"  Live file: {LIVE_FILE}")
    print(f"  YAML source: {YAML_PATH}")
    print(f"  YAML backups: {YAML_BACKUP_DIR}")
    print()
    print(f"To launch mGBA with live update:")
    print(f"  mgba-qt rom/working/penta_dragon_dx_FIXED.gb \\")
    print(f"    --script scripts/lua/live_palettes.lua")
    print()
    with PaletteHTTPServer((args.bind, args.port), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
