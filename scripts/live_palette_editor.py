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
  ARENA<d880>.BG<n>:<idx>=<hex>,...   (per-boss-arena BG row; the Lua bridge
                                       applies it only while D880 == <d880>)
where <hex> is 4-char BGR555 (e.g. "7FFF") or 6-char RGB hex.

Per-arena rows live in the optional YAML section `arena_bg_palettes`
(see scripts/arena_bg_palettes.py). Rows that are not overridden for an arena
fall back to the global `bg_palettes` rows, so global behavior is unchanged
when that section is absent.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arena_bg_palettes as abp  # noqa: E402

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

# Per-boss-arena BG rows. The rows each arena can actually show are derived
# from the same tile->palette tables the builder compiles into bank 13
# (scripts/arena_tables_data.py → build_v301_teleport._table_from_dict), so
# this panel cannot drift from the ROM the way the old hand-written list did.
# BG0 is always included: it is every arena's backdrop/unmapped cells.
ARENA_ROWS_USED = {key: abp.arena_rows_used(key) for key in abp.ARENA_KEYS}
BG_ROW_NAMES = [
    "Dungeon/floor", "cherry red", "purple", "green",
    "ice cyan", "yellow/red", "blue-gray", "steel/navy",
]


def arenas_sharing_row(row: int) -> list[str]:
    return [key for key in abp.ARENA_KEYS if row in ARENA_ROWS_USED[key]]


# Boss-palette YAML entries (FFBF 1-8 → boss-palette CRAM override).
# These are SEPARATE from stage-boss arena identification. They are
# the entries that v3.01's palette_loader writes when FFBF != 0
# (replacing the OBJ slot from the boss_slot_table). The names below
# are the YAML keys. FFBF 1/2 are verified Gargoyle/Spider minibosses;
# the legacy names for 3-8 remain builder-facing identifiers.
# The OBJ slot must equal the YAML `slot:` that bg_experiment.py compiles into
# the boss_slot_table at bank13:$68C0 (Knight=6, Angela=7). The editor used
# to preview FFBF 7/8 on OBJ4/OBJ5, i.e. on the wrong hardware row.
BOSS_PAL_ENTRIES = [
    # (FFBF value, YAML key, OBJ slot from boss_slot_table)
    (1, "Gargoyle",       6),
    (2, "Spider",         7),
    (3, "Boss3_Crimson",  6),
    (4, "Boss4_Ice",      7),
    (5, "Boss5_Void",     6),
    (6, "Boss6_Poison",   7),
    (7, "Boss7_Knight",   6),
    (8, "Angela",         7),
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
    # Optional per-arena BG rows (absent section == no overrides).
    palettes["ARENA"] = abp.parse_arena_bg_palettes(data)
    palettes["BG_labels"] = bg_keys
    palettes["OBJ_labels"] = obj_keys
    return palettes


def arena_live_lines(state: dict) -> list[str]:
    """Every per-arena override, D880-scoped for the Lua bridge.

    All overrides (not only rows edited this session) are emitted: the stream
    ROM may predate ROM support for `arena_bg_palettes`, so the live preview
    must supply saved arena rows itself. When the ROM does contain them the
    writes are identical and harmless.
    """
    lines = []
    for arena in abp.ARENA_KEYS:
        rows = state.get("ARENA", {}).get(arena) or {}
        for row in sorted(rows):
            entries = ",".join(
                f"{ci}={color.upper()}" for ci, color in enumerate(rows[row])
            )
            lines.append(
                f"ARENA{abp.ARENA_D880[arena]:02X}.BG{row}:{entries}"
            )
    return lines


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
        # Arena rows come after the global BG rows: Lua applies writes in
        # file order, so inside the matching arena they win over a global
        # edit of the same row, and outside it only the global row applies.
        lines.extend(arena_live_lines(state))
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


def update_arena_color(arena: str, pal: int, color: int, bgr: str) -> None:
    """Create/extend one arena row override (caller holds STATE_LOCK)."""
    rows = STATE.setdefault("ARENA", {}).setdefault(arena, {})
    if pal not in rows:
        # Start from the global row currently shown so the other three
        # colors keep matching what the host sees.
        rows[pal] = list(STATE["BG"][pal])
    rows[pal][color] = bgr
    STATE["ARENA"] = {
        key: dict(sorted(STATE["ARENA"][key].items()))
        for key in abp.ARENA_KEYS
        if STATE["ARENA"].get(key)
    }


def clear_arena_rows(arena: str, pal: int | None) -> list[int]:
    """Drop arena overrides; returns the rows that fell back to global."""
    rows = STATE.setdefault("ARENA", {}).get(arena) or {}
    cleared = sorted(rows) if pal is None else ([pal] if pal in rows else [])
    for row in cleared:
        rows.pop(row, None)
        # Re-assert the global row so CRAM leaves the arena color at once
        # instead of waiting for the ROM loader to repaint it.
        DIRTY["BG"].add(row)
    if not rows:
        STATE["ARENA"].pop(arena, None)
    return cleared


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

    # ─── Per-boss-arena BG row editor ───
    html_parts.append('<div class="section"><h2>Boss Arena BG Palettes (per arena)</h2>')
    html_parts.append(
        '<p style="font-size:0.85em;color:#888;">'
        'Pick a boss arena and edit the BG rows its tile table really uses '
        '(derived from <code>arena_tables_data.py</code>). Edits here are '
        '<strong>arena-scoped</strong>: the Lua bridge applies them only while '
        '<code>D880</code> equals that arena ($0C Shalamar … $14 Penta Dragon), '
        'so another boss sharing the same row keeps its own colors. Rows without '
        'an arena override show the global row (edited in "BG Palettes" below). '
        'Save writes <code>arena_bg_palettes.&lt;boss&gt;</code>. The current '
        'release ROM does not compile these rows yet: they are a live preview '
        'until the builder support lands and the ROM is rebuilt.</p>'
    )
    arena_state = STATE.get("ARENA", {})
    for arena, label, d880, _table in abp.ARENAS:
        used = ARENA_ROWS_USED[arena]
        overrides = arena_state.get(arena) or {}
        summary_rows = ", ".join(
            f"BG{row}{'*' if row in overrides else ''}" for row in used
        )
        html_parts.append(
            '<details style="margin:0.4em 0;border:1px solid #333;padding:0.4em;">'
        )
        html_parts.append(
            f'<summary style="cursor:pointer;font-weight:bold;">{label} '
            f'<span style="font-weight:normal;color:#aaa;">(D880=${d880:02X}; '
            f'uses {summary_rows}; * = arena override)</span></summary>'
        )
        html_parts.append(
            f'<button onclick="clearArena(\'{arena}\', null)">'
            f'Revert all {arena} rows to global</button>'
        )

        def arena_row(row: int) -> None:
            overridden = row in overrides
            colors = overrides.get(row) or STATE["BG"].get(row, ["0000"] * 4)
            sharing = [
                key for key in arenas_sharing_row(row) if key != arena
            ]
            share_text = (
                "global row also used by " + ", ".join(sharing)
                if sharing else "no other arena uses this row"
            )
            state_text = "ARENA OVERRIDE" if overridden else "global"
            html_parts.append(
                '<div class="pal" style="margin:0.3em 0;padding:0.3em;background:#1a1a1a;">'
            )
            html_parts.append(
                f'<div class="pal-name">BG{row} ({BG_ROW_NAMES[row]}) — '
                f'<strong id="arena-state-{arena}-{row}">{state_text}</strong>'
                f'<br><span style="font-size:0.8em;">{share_text}</span></div>'
            )
            html_parts.append('<div class="color-row" style="margin-top:0.3em;">')
            for ci, c in enumerate(colors):
                rgb = bgr555_to_rgb888(int(c, 16))
                html_parts.append(
                    f'<div><input type="color" value="{rgb}" '
                    f'data-kind="ARENA" data-arena="{arena}" data-pal="{row}" '
                    f'data-color="{ci}" data-overridden="{1 if overridden else 0}" '
                    f'onchange="updateArenaColor(this)">'
                    f'<div class="bgr" id="bgr-ARENA-{arena}-{row}-{ci}">'
                    f'{c.upper()}</div></div>'
                )
            html_parts.append(
                f'<button style="padding:0.1em 0.4em;font-size:0.8em;" '
                f'onclick="clearArena(\'{arena}\', {row})">global</button>'
            )
            html_parts.append("</div></div>")

        for row in used:
            arena_row(row)
        others = [row for row in range(8) if row not in used]
        html_parts.append(
            '<details style="margin-left:1em;"><summary style="cursor:pointer;'
            'color:#888;">Other rows (not produced by this arena\'s tile table)'
            '</summary>'
        )
        for row in others:
            arena_row(row)
        html_parts.append("</details>")
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
    if (kind === 'BG') {
        document.querySelectorAll(
            `input[data-kind="ARENA"][data-pal="${pal}"][data-color="${color}"][data-overridden="0"]`
        ).forEach(el => {
            el.value = input.value;
            const label = document.getElementById(
                `bgr-ARENA-${el.dataset.arena}-${pal}-${color}`);
            if (label) label.textContent = bgr;
        });
    }
    fetch('/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({kind, pal, color, bgr})
    });
}
function updateArenaColor(input) {
    const arena = input.dataset.arena;
    const pal = parseInt(input.dataset.pal);
    const color = parseInt(input.dataset.color);
    const bgr = rgb888_to_bgr555(input.value);
    document.getElementById(`bgr-ARENA-${arena}-${pal}-${color}`).textContent = bgr;
    document.querySelectorAll(
        `input[data-kind="ARENA"][data-arena="${arena}"][data-pal="${pal}"]`
    ).forEach(el => { el.dataset.overridden = "1"; });
    const badge = document.getElementById(`arena-state-${arena}-${pal}`);
    if (badge) badge.textContent = "ARENA OVERRIDE";
    fetch('/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({kind: 'ARENA', arena, pal, color, bgr})
    });
}
function clearArena(arena, pal) {
    fetch('/arena_clear', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({arena, pal})
    }).then(() => location.reload());
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
                if kind not in ("BG", "OBJ", "BOSS", "JET", "POWER", "ARENA"):
                    raise ValueError(
                        "kind must be BG, OBJ, BOSS, JET, POWER, or ARENA, "
                        f"got {kind!r}"
                    )
                arena = None
                if kind == "ARENA":
                    arena = str(data.get("arena", ""))
                    if arena not in abp.ARENA_D880:
                        raise ValueError(f"unknown arena: {arena!r}")
                valid_palettes = {
                    "BG": range(8),
                    "OBJ": range(8),
                    "BOSS": range(1, 9),
                    "JET": range(1, 3),
                    "POWER": range(1, 4),
                    "ARENA": range(8),
                }[kind]
                if pal not in valid_palettes:
                    expected = {
                        "BG": "0-7",
                        "OBJ": "0-7",
                        "BOSS": "1-8",
                        "JET": "1-2",
                        "POWER": "1-3",
                        "ARENA": "0-7",
                    }[kind]
                    raise ValueError(f"{kind} palette must be {expected}, got {pal}")
                if color not in range(4):
                    raise ValueError(f"color must be 0-3, got {color}")
                if not re.fullmatch(r"[0-7][0-9A-F]{3}", bgr):
                    raise ValueError(f"invalid BGR555 value: {bgr!r}")
                with STATE_LOCK:
                    if kind == "ARENA":
                        update_arena_color(arena, pal, color, bgr)
                    else:
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
        elif url.path == "/arena_clear":
            try:
                data = json.loads(body)
                arena = str(data.get("arena", ""))
                if arena not in abp.ARENA_D880:
                    raise ValueError(f"unknown arena: {arena!r}")
                pal = data.get("pal")
                if pal is not None:
                    pal = int(pal)
                    if pal not in range(8):
                        raise ValueError(f"ARENA palette must be 0-7, got {pal}")
                with STATE_LOCK:
                    cleared = clear_arena_rows(arena, pal)
                    write_live_file(STATE, DIRTY)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(
                    f"{arena}: reverted rows {cleared} to global".encode()
                )
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/reload":
            with STATE_LOCK:
                previous_arena = STATE.get("ARENA", {})
                STATE = load_yaml_palettes()
                # Rows that had a session-only arena override must be
                # re-asserted from the global row so CRAM does not keep the
                # discarded arena color.
                for arena, rows in previous_arena.items():
                    for row in rows:
                        if row not in (STATE["ARENA"].get(arena) or {}):
                            DIRTY["BG"].add(row)
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
        arena_state = STATE.get("ARENA", {})
        updated = abp.replace_section(updated, arena_state)
        # Refuse to write a file that would not read back as exactly the
        # state on screen (both the arena section and every global row).
        document = yaml.safe_load(updated)
        if abp.parse_arena_bg_palettes(document) != {
            key: dict(sorted(rows.items()))
            for key, rows in arena_state.items() if rows
        }:
            raise RuntimeError("arena_bg_palettes did not round-trip; not saved")
        for index, key in enumerate(STATE.get("BG_labels", [])):
            saved = [c.upper() for c in document["bg_palettes"][key]["colors"]]
            if saved != [c.upper() for c in STATE["BG"][index]]:
                raise RuntimeError(f"bg_palettes.{key} did not round-trip")
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
