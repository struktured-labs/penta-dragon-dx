#!/usr/bin/env python3
"""Live palette editor — browser-based GUI for tuning Penta Dragon DX CGB colors.

Workflow:
  1. Start this script:  python3 scripts/live_palette_editor.py
  2. Open http://localhost:8077 in browser
  3. Launch mGBA with live palette script:
       mgba-qt rom/working/penta_dragon_dx_v301.gb --script scripts/lua/live_palettes.lua
  4. Adjust colors in browser. Changes apply to running game within ~0.5s.

The browser saves color picks to /tmp/live_palettes.txt. The mGBA Lua
script polls that file every 30 frames (~0.5s) and rewrites CGB palette
CRAM (BCPS/BCPD for BG, OCPS/OCPD for OBJ) with the new values.

To persist tuned colors back to the YAML, click "Save to YAML" — appends
the current state to palettes/penta_palettes_v097.yaml.

Color format in /tmp/live_palettes.txt:
  BG<n>:<idx>=<hex>,<idx>=<hex>,...
  OBJ<n>:<idx>=<hex>,<idx>=<hex>,...
where <hex> is 4-char BGR555 (e.g. "7FFF") or 6-char RGB hex.

Default palettes are loaded from palettes/penta_palettes_v097.yaml.
"""
import http.server
import json
import socketserver
import threading
import time
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import yaml
except ImportError:
    print("Install: pip install pyyaml")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
LIVE_FILE = Path("/tmp/live_palettes.txt")
YAML_PATH = ROOT / "palettes" / "penta_palettes_v097.yaml"

PORT = 8077

# Stage boss metadata.
#
# The 9 stage bosses are dispatched by FFBA (level counter 0-8) via the
# arena jump table at bank 2:0x6EA6. Each arena routine self-publishes
# D880 + FFB7 at entry. Names + D880 values from
# docs/boss_arena_routines.md.
#
# FFBA is the canonical identifier. FFBF is a SEPARATE flag used for
# mini-bosses (Gargoyle=1, Spider=2) and the boss_palette_table
# (which has only 6 "stage boss" entries — Boss3_Crimson..Angela —
# whose direct correspondence to in-game named bosses is unverified,
# so we use the YAML keys as-is for color tuning).
#
# Teleport caveat: memory note from runtime_probe_final.md says
# "raw D880 write reverts on next frame — need FFD3 event sequence
# + room conditions". So teleport here uses FORCE-EVERY-FRAME to
# hold the state, which still won't load boss tile data but at
# least keeps the arena state byte set.
STAGE_BOSSES = [
    # (FFBA, name, arena D880, hint about palette source)
    # Indexes 7 and 8 corrected 2026-06-03 — empirically Angela=7,
    # Penta Dragon=8 (user-verified via DX Teleport buttons).
    # docs/boss_arena_routines.md previously had these swapped; the
    # reverse_engineering notes (gap_boss_arena_setup.md) were correct.
    (0, "Shalamar (Stage 1)",      0x0C, "uses tile-range OBJ pal"),
    (1, "Riff (Stage 2)",          0x0D, "uses tile-range OBJ pal"),
    (2, "Crystal Dragon (Stage 3)", 0x0E, "uses tile-range OBJ pal"),
    (3, "Cameo (Stage 4)",         0x0F, "uses tile-range OBJ pal"),
    (4, "Ted (Stage 5)",           0x10, "uses tile-range OBJ pal"),
    (5, "Troop (Stage 6)",         0x11, "uses tile-range OBJ pal"),
    (6, "Faze (Stage 7)",          0x12, "uses tile-range OBJ pal"),
    (7, "Angela",                  0x13, "uses tile-range OBJ pal"),
    (8, "Penta Dragon (Final)",    0x14, "uses tile-range OBJ pal"),
]

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


# Boss-palette YAML entries (FFBF 3-8 → boss-palette CRAM override).
# These are SEPARATE from stage-boss arena identification. They are
# the entries that v3.01's palette_loader writes when FFBF != 0
# (replacing the OBJ slot from the boss_slot_table). The names below
# are the YAML keys, not necessarily the in-game bosses — we'd need
# more reverse engineering to confirm which FFBF value corresponds
# to which named in-game boss (if any).
BOSS_PAL_ENTRIES = [
    # (FFBF value, YAML key, OBJ slot from boss_slot_table)
    (3, "Boss3_Crimson",  6),
    (4, "Boss4_Ice",      7),
    (5, "Boss5_Void",     6),
    (6, "Boss6_Poison",   7),
    (7, "Boss7_Knight",   4),
    (8, "Angela",         5),
]


def bgr555_to_rgb888(val15: int) -> str:
    r5 = val15 & 0x1F
    g5 = (val15 >> 5) & 0x1F
    b5 = (val15 >> 10) & 0x1F
    r = (r5 * 255) // 31
    g = (g5 * 255) // 31
    b = (b5 * 255) // 31
    return f"#{r:02x}{g:02x}{b:02x}"


def rgb888_to_bgr555(rgb_hex: str) -> int:
    s = rgb_hex.lstrip("#")
    r = int(s[0:2], 16) if len(s) >= 6 else 0
    g = int(s[2:4], 16) if len(s) >= 6 else 0
    b = int(s[4:6], 16) if len(s) >= 6 else 0
    r5 = min(31, (r * 31) // 255)
    g5 = min(31, (g * 31) // 255)
    b5 = min(31, (b * 31) // 255)
    return (b5 << 10) | (g5 << 5) | r5


def load_yaml_palettes() -> dict:
    """Returns {kind: {pal_idx: [color_hex × 4]}}."""
    with open(YAML_PATH) as f:
        data = yaml.safe_load(f)
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    obj_keys = ['EnemyProjectile', 'SaraDragon', 'SaraWitch',
                'SaraProjectileAndCrow', 'Hornets', 'OrcGround',
                'Humanoid', 'Catfish']
    palettes = {"BG": {}, "OBJ": {}, "BOSS": {}}
    for i, k in enumerate(bg_keys):
        entry = data.get('bg_palettes', {}).get(k, {})
        palettes["BG"][i] = entry.get('colors', ["7FFF", "5294", "2108", "0000"])
    for i, k in enumerate(obj_keys):
        entry = data.get('obj_palettes', {}).get(k, {})
        palettes["OBJ"][i] = entry.get('colors', ["0000", "7C1F", "4C0F", "0000"])
    # Boss-palette override entries from YAML.
    for ffbf, yaml_key, slot in BOSS_PAL_ENTRIES:
        entry = data.get('boss_palettes', {}).get(yaml_key, {})
        palettes["BOSS"][ffbf] = entry.get('colors', ["0000", "7C1F", "4C0F", "0000"])
    palettes["BG_labels"] = bg_keys
    palettes["OBJ_labels"] = obj_keys
    return palettes


def write_live_file(state: dict, preview_ffbf: int = 0, force_arena: dict = None,
                    dx_teleport: int = 0):
    """Write the current state dict to LIVE_FILE in mGBA-readable format.

    Optional `preview_ffbf`: forces FFBF every frame for boss palette preview.

    Optional `force_arena`: dict with ffba/d880/ffb7 — forced every frame
    (held state, no proper init).

    Optional `dx_teleport`: 1-9 = one-shot DX teleport request. Lua writes
    DF0A = this value, ROM-side hook in v3.01 colorize handler JPs to
    bank2:0x4000 with FFBA = dx_teleport - 1.
    """
    lines = ["# Auto-generated by live_palette_editor.py"]
    for kind in ("BG", "OBJ"):
        for pal_idx, colors in state[kind].items():
            entries = ",".join(f"{ci}={c.upper()}" for ci, c in enumerate(colors))
            lines.append(f"{kind}{pal_idx}:{entries}")
    if preview_ffbf:
        slot = next((s for f, k, s in BOSS_PAL_ENTRIES if f == preview_ffbf), 6)
        yaml_key = next((k for f, k, s in BOSS_PAL_ENTRIES if f == preview_ffbf), "?")
        colors = state["BOSS"].get(preview_ffbf, ["0000"] * 4)
        entries = ",".join(f"{ci}={c.upper()}" for ci, c in enumerate(colors))
        lines.append(f"# Boss palette preview: FFBF={preview_ffbf} ({yaml_key}) → OBJ slot {slot}")
        lines.append(f"OBJ{slot}:{entries}")
        lines.append(f"FFBF:{preview_ffbf}")
    if force_arena:
        if "ffba" in force_arena:
            lines.append(f"FFBA:{force_arena['ffba']}")
        if "d880" in force_arena:
            lines.append(f"D880:0x{force_arena['d880']:02X}")
        if "ffb7" in force_arena:
            lines.append(f"FFB7:0x{force_arena['ffb7']:02X}")
    if dx_teleport:
        lines.append(f"# DX teleport: DF0A = {dx_teleport} → FFBA = {dx_teleport - 1}")
        lines.append(f"DX:{dx_teleport}")
    LIVE_FILE.write_text("\n".join(lines) + "\n")


# Global state
STATE = load_yaml_palettes()
PREVIEW_FFBF = 0  # 0 = no preview, 3..8 = preview this boss palette
FORCE_ARENA = None  # None or {ffba, d880, ffb7} when teleporting
write_live_file(STATE)


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
<button onclick="reload()">Reload from YAML</button>
<button onclick="save()">Save to YAML</button>
<button onclick="copyState()">Copy current as JSON</button>
"""]

    # DX Teleport section. Writes DX:N to /tmp/live_palettes.txt → Lua
    # writes DF0A = N → ROM-side teleport hook consumes it (when wired).
    # Lua workaround (2026-06-03): instead of writing DF0A for a ROM
    # consumer, Lua simulates the SELECT+START combo: pre-write FFBA so
    # the ROM's INC lands on the target, then pulse FF93=0x0C for ~6 frames
    # via emu:setKeys. Bypasses the v17 freeze entirely.
    # Requires: rom/working/penta_dragon_dx_teleport.gb (v16, tag
    # v3.01-teleport-all-bosses). Tested working in mgba 0.10.5.
    html_parts.append('<div class="section"><h2>DX Teleport</h2>')
    html_parts.append('<p style="font-size:0.85em;color:#888;">'
                      'Click any boss → Lua pre-writes FFBA and pulses SELECT+START '
                      '→ ROM combo handler does INC + arena init. Requires the v16 '
                      '<code>penta_dragon_dx_teleport.gb</code> ROM and dungeon state '
                      '(D880=0x02). Cycles cleanly through all 9 bosses.</p>')
    html_parts.append('<div style="display:flex;flex-wrap:wrap;gap:0.3em;">')
    for ffba, name, _d880, _hint in STAGE_BOSSES:
        html_parts.append(
            f'<button onclick="dxTeleport({ffba + 1})">'
            f'{name}<br><span style="font-size:0.7em;color:#aaa;">DF0A={ffba + 1}</span></button>'
        )
    html_parts.append("</div></div>")

    # ─── Per-stage-boss body palette editor ───
    # Shows the BG palette indices each boss's bg_table assigns to body
    # regions (mirrors _bg_table_<boss>() in build_v301_teleport.py).
    # Editing the colors here writes to live CRAM via /tmp/live_palettes.txt.
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
        html_parts.append('<div style="margin-top:0.6em;">'
                          f'<button onclick="dxTeleport({ffba + 1})" style="margin-bottom:0.4em;">'
                          f'Teleport to {name}</button></div>')
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

    # ─── Soft state-byte hold (legacy fallback if DX hook not present) ───
    html_parts.append('<div class="section"><h2>State-byte Hold (legacy)</h2>')
    html_parts.append('<p style="font-size:0.85em;color:#888;">'
                      'Holds FFBA + D880 + FFB7 every frame WITHOUT calling the arena '
                      'routine. Does NOT load boss tile data — visual will be wrong. '
                      'Use only if DX teleport above doesn\'t work (e.g., older ROM).</p>')
    current = f"FFBA={FORCE_ARENA['ffba']}, D880=0x{FORCE_ARENA['d880']:02X}" if FORCE_ARENA else "none"
    html_parts.append(f'<div style="margin-bottom:0.5em;color:#cc4;">Holding: {current}</div>')
    html_parts.append('<div style="display:flex;flex-wrap:wrap;gap:0.3em;">')
    html_parts.append('<button onclick="teleport(-1, 0)">Clear hold</button>')
    for ffba, name, d880, _hint in STAGE_BOSSES:
        active = " style=\"background:#284;\"" if FORCE_ARENA and FORCE_ARENA.get("ffba") == ffba else ""
        html_parts.append(
            f'<button{active} onclick="teleport({ffba}, 0x{d880:02X})">'
            f'{name}<br><span style="font-size:0.7em;color:#aaa;">FFBA={ffba} D880=0x{d880:02X}</span></button>'
        )
    html_parts.append("</div></div>")

    # ─── Boss palette overrides (FFBF mechanism) ───
    # The boss_palette_table entries (Boss3_Crimson..Angela) are
    # FFBF-based overrides that v3.01's palette_loader writes to OBJ
    # slot when FFBF != 0. Their direct correspondence to in-game
    # named bosses is unverified — these are just 6 color presets
    # that get applied when their FFBF value is active.
    html_parts.append('<div class="section"><h2>Boss Palette Overrides (FFBF 3-8)</h2>')
    html_parts.append('<p style="font-size:0.85em;color:#888;">'
                      'These are the boss_palette_table entries in the ROM. When FFBF=N (1-8) is active, '
                      'v3.01\'s palette_loader writes the matching entry to OBJ slot per boss_slot_table = [6,7,6,7,6,7,4,5]. '
                      'FFBF 1-2 are mini-bosses (Gargoyle, Spider) — excluded. '
                      '<strong>Preview</strong> forces FFBF every frame so the boss palette code path runs.</p>')
    html_parts.append(f'<div><label><input type="radio" name="preview" value="0" {"checked" if PREVIEW_FFBF == 0 else ""} onchange="setPreview(0)"> No preview</label></div>')
    for ffbf, yaml_key, slot in BOSS_PAL_ENTRIES:
        colors = STATE["BOSS"].get(ffbf, ["0000"] * 4)
        checked = "checked" if PREVIEW_FFBF == ffbf else ""
        html_parts.append(f'<div class="pal" style="display:block;margin:0.5em 0;">')
        html_parts.append(f'<div style="display:flex;align-items:center;gap:0.5em;">')
        html_parts.append(f'<label><input type="radio" name="preview" value="{ffbf}" {checked} onchange="setPreview({ffbf})"> Preview</label>')
        html_parts.append(f'<span class="pal-name">{yaml_key} (FFBF={ffbf}, → OBJ slot {slot})</span>')
        html_parts.append(f'</div>')
        html_parts.append('<div class="color-row" style="margin-top:0.3em;">')
        for ci, c in enumerate(colors):
            val15 = int(c, 16)
            rgb = bgr555_to_rgb888(val15)
            html_parts.append(
                f'<div><input type="color" value="{rgb}" '
                f'data-kind="BOSS" data-pal="{ffbf}" data-color="{ci}" '
                f'onchange="updateColor(this)">'
                f'<div class="bgr" id="bgr-BOSS-{ffbf}-{ci}">{c.upper()}</div></div>'
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
    const r5 = Math.min(31, Math.floor(r * 31 / 255));
    const g5 = Math.min(31, Math.floor(g * 31 / 255));
    const b5 = Math.min(31, Math.floor(b * 31 / 255));
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
function setPreview(ffbf) {
    fetch('/preview', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ffbf})
    });
}
function teleport(ffba, d880) {
    fetch('/teleport', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ffba, d880})
    }).then(r => r.text()).then(t => {
        console.log('teleport:', t);
        location.reload();
    });
}
function dxTeleport(df0a) {
    // df0a = 1..9 (FFBA + 1)
    fetch('/dx_teleport', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({df0a})
    }).then(r => r.text()).then(t => console.log('dx_teleport:', t));
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
            body = render_index().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/state":
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
        global STATE, PREVIEW_FFBF, FORCE_ARENA
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
                STATE[kind][pal][color] = bgr
                write_live_file(STATE, preview_ffbf=PREVIEW_FFBF, force_arena=FORCE_ARENA)
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/preview":
            try:
                data = json.loads(body)
                PREVIEW_FFBF = int(data.get("ffbf", 0))
                write_live_file(STATE, preview_ffbf=PREVIEW_FFBF, force_arena=FORCE_ARENA)
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/dx_teleport":
            try:
                data = json.loads(body)
                df0a = int(data.get("df0a", 0))
                if df0a < 1 or df0a > 9:
                    raise ValueError(f"df0a must be 1-9, got {df0a}")
                # One-shot write: write_live_file with dx_teleport=df0a.
                # Lua picks up DX:N once, writes DF0A, clears.
                write_live_file(STATE, preview_ffbf=PREVIEW_FFBF, force_arena=FORCE_ARENA, dx_teleport=df0a)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"DX teleport requested: DF0A={df0a} → FFBA={df0a-1}".encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/teleport":
            try:
                data = json.loads(body)
                ffba = int(data.get("ffba", -1))
                d880 = int(data.get("d880", 0))
                if ffba < 0:
                    # Clear teleport
                    FORCE_ARENA = None
                    msg = "teleport cleared"
                else:
                    # Hold arena state every frame.
                    FORCE_ARENA = {
                        "ffba": ffba,
                        "d880": d880,
                        "ffb7": d880,
                    }
                    msg = f"holding arena: FFBA={ffba}, D880=0x{d880:02X}, FFB7=0x{d880:02X}"
                write_live_file(STATE, preview_ffbf=PREVIEW_FFBF, force_arena=FORCE_ARENA)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(msg.encode())
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"error: {e}".encode())
        elif url.path == "/reload":
            STATE = load_yaml_palettes()
            write_live_file(STATE, preview_ffbf=PREVIEW_FFBF, force_arena=FORCE_ARENA)
            self.send_response(200)
            self.end_headers()
        elif url.path == "/save":
            self.save_to_yaml()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Saved to {YAML_PATH}".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def save_to_yaml(self):
        """Update the YAML file with current STATE colors."""
        with open(YAML_PATH) as f:
            data = yaml.safe_load(f)
        bg_keys = STATE.get("BG_labels", [])
        obj_keys = STATE.get("OBJ_labels", [])
        for i, k in enumerate(bg_keys):
            if k in data.get('bg_palettes', {}):
                data['bg_palettes'][k]['colors'] = STATE["BG"][i]
        for i, k in enumerate(obj_keys):
            if k in data.get('obj_palettes', {}):
                data['obj_palettes'][k]['colors'] = STATE["OBJ"][i]
        # Boss-palette overrides
        for ffbf, yaml_key, slot in BOSS_PAL_ENTRIES:
            if yaml_key in data.get('boss_palettes', {}):
                data['boss_palettes'][yaml_key]['colors'] = STATE["BOSS"][ffbf]
        with open(YAML_PATH, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=None)


def main():
    print(f"Live palette editor")
    print(f"  Browser: http://localhost:{PORT}")
    print(f"  mGBA Lua script: scripts/lua/live_palettes.lua")
    print(f"  Live file: {LIVE_FILE}")
    print(f"  YAML source: {YAML_PATH}")
    print()
    print(f"To launch mGBA with live update:")
    print(f"  mgba-qt rom/working/penta_dragon_dx_v301.gb \\")
    print(f"    --script scripts/lua/live_palettes.lua")
    print()
    with socketserver.TCPServer(("", PORT), Handler) as srv:
        srv.allow_reuse_address = True
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
