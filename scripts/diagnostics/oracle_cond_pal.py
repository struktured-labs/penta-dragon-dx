#!/usr/bin/env python3
"""Independent Python oracle for cond_pal + palette_loader logic.

Per dr-mario-rl's pattern (session-intercom msg 1910, 2026-06-30):
  - HARNESS = mGBA-headless runs actual SM83 opcodes on the wrapper
  - ORACLE  = this file: plain Python implementing ONLY the logic spec
  - Compare outputs cell-by-cell over N random states; match = real
    confidence that bg_experiment.py's palette_loader bytes implement
    the YAML spec correctly.

This is INDEPENDENT from the assembly — written from the YAML + the
documented behavior in create_palette_loader/create_conditional_palette
docstrings, not extracted from the byte sequence. A bug in
bg_experiment.py and a bug here are unlikely to coincide.

Usage:
  python oracle_cond_pal.py                  # self-check on canonical states
  python oracle_cond_pal.py --diff ROM.gb    # diff vs mGBA headless harness
  python oracle_cond_pal.py --fuzz 500       # 500 random states sanity
"""

from __future__ import annotations
import argparse
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("yaml module required (uv add pyyaml or pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PALETTE_YAML = REPO_ROOT / "palettes" / "penta_palettes_v097.yaml"


def color_to_bytes(hex_str: str) -> tuple[int, int]:
    """CGB BGR15 hex (e.g. '7FFF') → (lo, hi) byte pair."""
    val = int(hex_str, 16) & 0x7FFF
    return (val & 0xFF, (val >> 8) & 0xFF)


def palette_to_bytes(colors: list[str]) -> bytes:
    """4 hex colors → 8 bytes (lo,hi × 4)."""
    out = bytearray()
    for c in colors:
        lo, hi = color_to_bytes(c)
        out.extend([lo, hi])
    return bytes(out)


@dataclass
class PaletteSpec:
    """Parsed YAML → all the palette tables the oracle needs."""
    bg: list[bytes] = field(default_factory=list)           # 8 × 8 bytes
    obj: list[bytes] = field(default_factory=list)          # 8 × 8 bytes
    sara_witch_jet: bytes = b""                              # 8 bytes (OBP-2 jet variant)
    sara_dragon_jet: bytes = b""                             # 8 bytes (OBP-1 jet variant)
    spiral_proj: bytes = b""                                 # 8 bytes (OBP-0 FFC0=1)
    shield_proj: bytes = b""                                 # 8 bytes (OBP-0 FFC0=2)
    turbo_proj: bytes = b""                                  # 8 bytes (OBP-0 FFC0=3+)
    boss_pal_table: list[bytes] = field(default_factory=list)   # 8 × 8 bytes (FFBF=1..8)
    boss_slot_table: list[int] = field(default_factory=list)    # FFBF=N → OBP slot

    @classmethod
    def load(cls, yaml_path: Path = PALETTE_YAML) -> "PaletteSpec":
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        spec = cls()

        # BG: 8 palettes named Dungeon, BG1..BG7
        bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
        bg_palettes = data.get('bg_palettes', {})
        for key in bg_keys:
            colors = bg_palettes.get(key, {}).get('colors',
                                                  ["7FFF", "5294", "2108", "0000"])
            spec.bg.append(palette_to_bytes(colors))
        # Build override: BGP7 ← BGP0 (Dungeon) per build_v301_gdma.py:417
        # ("hide stale CGB boot-ROM attrs"). YAML BG7 definition is dead.
        # NOTE: 2026-06-30 user-requested YAML-vs-game drift hunt — leave
        # this commented to surface the BG7 override as a real drift case.
        # spec.bg[7] = spec.bg[0]

        # OBJ: 8 palettes (slot index → key)
        obj_key_map = {
            0: ('EnemyProjectile', ["0000", "7C1F", "5817", "3010"]),
            1: ('SaraDragon',      ["0000", "03E0", "01C0", "0000"]),
            2: ('SaraWitch',       ["0000", "2EBE", "511F", "0842"]),
            3: ('SaraProjectileAndCrow', ["0000", "001F", "0017", "000F"]),
            4: ('Hornets',         ["0000", "03FF", "00DF", "0000"]),
            5: ('OrcGround',       ["0000", "02A0", "0160", "0000"]),
            6: ('Humanoid',        ["0000", "7C1F", "4C0F", "0000"]),
            7: ('Catfish',         ["0000", "7FE0", "3CC0", "0000"]),
        }
        obj_palettes = data.get('obj_palettes', {})
        for i in range(8):
            key, fallback = obj_key_map[i]
            colors = obj_palettes.get(key, {}).get('colors', fallback)
            spec.obj.append(palette_to_bytes(colors))

        # Jet variants (FFD0=1 overrides OBP-1 and OBP-2)
        spec.sara_witch_jet = palette_to_bytes(
            obj_palettes.get('SaraWitchJet', {}).get(
                'colors', ["0000", "7C1F", "5817", "3010"]))
        spec.sara_dragon_jet = palette_to_bytes(
            obj_palettes.get('SaraDragonJet', {}).get(
                'colors', ["0000", "7FE0", "4EC0", "2D80"]))

        # FFC0-conditional OBP-0 swap
        powerups = data.get('powerup_palettes', {})
        spec.spiral_proj = palette_to_bytes(
            powerups.get('SpiralProjectile', {}).get(
                'colors', ["0000", "7FE0", "5EC0", "3E80"]))
        spec.shield_proj = palette_to_bytes(
            powerups.get('ShieldProjectile', {}).get(
                'colors', ["0000", "03FF", "02BF", "019F"]))
        spec.turbo_proj = palette_to_bytes(
            powerups.get('TurboProjectile', {}).get(
                'colors', ["0000", "00FF", "00BF", "005F"]))

        # Boss table (FFBF=1..8 → OBP slot + colors)
        boss_keys = ['Gargoyle', 'Spider', 'Boss3_Crimson', 'Boss4_Ice',
                     'Boss5_Void', 'Boss6_Poison', 'Boss7_Knight', 'Angela']
        boss_data = data.get('boss_palettes', {})
        for key in boss_keys:
            entry = boss_data.get(key, {})
            colors = entry.get('colors', ["0000", "7FFF", "5294", "2108"])
            slot = entry.get('slot', 6)
            spec.boss_pal_table.append(palette_to_bytes(colors))
            spec.boss_slot_table.append(slot)

        return spec


@dataclass
class GameState:
    """The 5 game-state bytes that drive cond_pal + palette_loader."""
    ffbe: int = 0   # Sara form (0=witch, 1=dragon)
    ffbf: int = 0   # Boss slot (0=none, 1-8=boss N)
    ffc0: int = 0   # Projectile mode (0=default, 1=spiral, 2=shield, 3+=turbo)
    ffd0: int = 0   # Jet form flag (0=base, 1=jet)
    ffa9: int = 0   # cond_pal cache hash (prev frame's hash)


@dataclass
class CRAMResult:
    """What cond_pal+palette_loader should leave in CRAM."""
    bgp: list[bytes] = field(default_factory=list)  # 8 × 8 bytes (BGP-0..7)
    obp: list[bytes] = field(default_factory=list)  # 8 × 8 bytes (OBP-0..7)
    new_ffa9: int = 0                                # post-frame cache hash
    fired_palette_loader: bool = False               # did cache miss?


def cond_pal_oracle(state: GameState, spec: PaletteSpec,
                    prev_cram: CRAMResult | None = None) -> CRAMResult:
    """The spec, in Python.

    Step 1 (cond_pal): hash = (FFBE^FFBF^FFC0^FFD0) + 1
                       if hash == FFA9 (cached): RET (no work)
                       else: FFA9 = hash; fall through to palette_loader

    Step 2 (palette_loader, only on cache miss):
       - Load BG palettes 0..7 from bg_data (constant from ROM)
       - Load OBP-0 from FFC0-conditional source:
            FFC0=0: obj[0] (EnemyProjectile, default)
            FFC0=1: spiral_proj
            FFC0=2: shield_proj
            FFC0=3+: turbo_proj
       - Load OBP-1 from FFD0-conditional source:
            FFD0=1: sara_dragon_jet (jet form)
            else:   obj[1] (SaraDragon)
       - Load OBP-2 from FFD0-conditional source:
            FFD0=1: sara_witch_jet (jet form)
            else:   obj[2] (SaraWitch)
       - Load OBP-3+4 from obj[3] then obj[4] (24 bytes from sara_proj_addr)
       - Load OBP-6 from obj[6] (Humanoid)
       - Load OBP-7 from obj[7] (Catfish)
       - If FFBF != 0: boss_pal injection
            slot = boss_slot_table[FFBF-1]
            OBP[slot] = boss_pal_table[FFBF-1]   (overwrites Humanoid or Catfish)
    """
    # --- cond_pal hash check ---
    hash_val = ((state.ffbe ^ state.ffbf ^ state.ffc0 ^ state.ffd0) + 1) & 0xFF

    if hash_val == state.ffa9:
        # Cache hit — palette_loader did not fire. CRAM unchanged from prev.
        result = CRAMResult(
            bgp=list(prev_cram.bgp) if prev_cram else [b"\x00" * 8] * 8,
            obp=list(prev_cram.obp) if prev_cram else [b"\x00" * 8] * 8,
            new_ffa9=state.ffa9,
            fired_palette_loader=False,
        )
        return result

    # --- palette_loader fires ---
    result = CRAMResult(new_ffa9=hash_val, fired_palette_loader=True)

    # BG palettes 0..7: load from bg_data (no conditions)
    result.bgp = list(spec.bg)

    # OBP-0: FFC0-conditional
    if state.ffc0 == 0:
        obp0 = spec.obj[0]
    elif state.ffc0 == 1:
        obp0 = spec.spiral_proj
    elif state.ffc0 == 2:
        obp0 = spec.shield_proj
    else:  # 3+
        obp0 = spec.turbo_proj

    # OBP-1: FFD0=1 → dragon jet, else SaraDragon
    obp1 = spec.sara_dragon_jet if state.ffd0 == 1 else spec.obj[1]
    # OBP-2: FFD0=1 → witch jet, else SaraWitch
    obp2 = spec.sara_witch_jet if state.ffd0 == 1 else spec.obj[2]
    # OBP-3: SaraProjectileAndCrow (no condition)
    obp3 = spec.obj[3]
    # OBP-4: loaded as continuation (24 bytes from sara_proj_addr covers OBP-3+4+5
    # in the asm; the asm reads 24 bytes starting at sara_proj_addr which is
    # obj[3], so OBP-3=obj[3], OBP-4=obj[4], OBP-5=obj[5])
    obp4 = spec.obj[4]
    obp5 = spec.obj[5]
    # OBP-6: Humanoid (default; boss_pal can override)
    obp6 = spec.obj[6]
    # OBP-7: Catfish (default; boss_pal can override)
    obp7 = spec.obj[7]

    obp = [obp0, obp1, obp2, obp3, obp4, obp5, obp6, obp7]

    # Boss palette injection (if FFBF != 0)
    if state.ffbf != 0 and 1 <= state.ffbf <= 8:
        idx = state.ffbf - 1
        slot = spec.boss_slot_table[idx]
        if 0 <= slot < 8:
            obp[slot] = spec.boss_pal_table[idx]

    result.obp = obp
    return result


# -----------------------------------------------------------------------------
# Self-test: canonical states with known expected CRAM
# -----------------------------------------------------------------------------

def self_test(spec: PaletteSpec) -> tuple[int, int]:
    """Test canonical (state → expected key CRAM bytes) tuples.
    Returns (passed, total)."""
    passed = total = 0
    cases = [
        # (description, state, expected_obp2_lo_idx1)
        ("Sara witch baseline (FFBE=0, FFD0=0) → OBP-2 = SaraWitch peach 0x2EBE",
         GameState(ffbe=0, ffd0=0), 2, 1, 0x2EBE),
        ("Sara dragon (FFBE=1, FFD0=0) → OBP-1 = SaraDragon green 0x03E0",
         GameState(ffbe=1, ffd0=0), 1, 1, 0x03E0),
        ("Sara jet (FFD0=1) → OBP-2 = SaraWitchJet (idx 1, jet ROM source)",
         GameState(ffd0=1), 2, 1, None),  # None = just verify it's NOT 0x2EBE
        ("FFBF=1 Gargoyle → OBP-6 = Gargoyle (slot 6)",
         GameState(ffbf=1), 6, 1, None),  # idx 1 — distinctive Gargoyle red
        ("FFC0=1 spiral → OBP-0 = SpiralProjectile",
         GameState(ffc0=1), 0, 1, None),  # NOT default EnemyProjectile
    ]
    for desc, state, obp_idx, color_idx, expected_color in cases:
        total += 1
        result = cond_pal_oracle(state, spec)
        # Extract color from CRAM bytes (lo, hi) at idx
        cram_bytes = result.obp[obp_idx]
        lo = cram_bytes[color_idx * 2]
        hi = cram_bytes[color_idx * 2 + 1]
        actual_color = lo | (hi << 8)

        if expected_color is not None:
            ok = actual_color == expected_color
        else:
            # Just verify it changed from the default for this slot
            default = spec.obj[obp_idx]
            default_color = default[color_idx * 2] | (default[color_idx * 2 + 1] << 8)
            ok = actual_color != default_color

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {desc}")
        if not ok:
            print(f"         got 0x{actual_color:04X}, expected "
                  f"{'0x' + format(expected_color, '04X') if expected_color else 'NOT default 0x' + format(default_color, '04X')}")
        passed += ok

    return passed, total


def fuzz(spec: PaletteSpec, n: int) -> tuple[int, int]:
    """Run N random states; verify oracle doesn't crash and outputs are coherent.
    Returns (passed, total)."""
    passed = total = 0
    rng = random.Random(42)
    prev_result: CRAMResult | None = None

    for _ in range(n):
        state = GameState(
            ffbe=rng.choice([0, 1]),
            ffbf=rng.randint(0, 8),
            ffc0=rng.randint(0, 5),
            ffd0=rng.choice([0, 1]),
            ffa9=prev_result.new_ffa9 if prev_result else 0,
        )
        try:
            result = cond_pal_oracle(state, spec, prev_result)
            total += 1
            # Coherence checks
            assert len(result.bgp) == 8 and all(len(p) == 8 for p in result.bgp), \
                f"BGP malformed: {[len(p) for p in result.bgp]}"
            assert len(result.obp) == 8 and all(len(p) == 8 for p in result.obp), \
                f"OBP malformed: {[len(p) for p in result.obp]}"
            assert 0 <= result.new_ffa9 <= 0xFF, f"hash out of range: {result.new_ffa9}"
            # Hash math
            expected_hash = ((state.ffbe ^ state.ffbf ^ state.ffc0 ^ state.ffd0) + 1) & 0xFF
            if state.ffa9 == expected_hash:
                assert not result.fired_palette_loader, "should be cache hit"
            else:
                assert result.fired_palette_loader, "should be cache miss"
                assert result.new_ffa9 == expected_hash, "hash mismatch"
            passed += 1
            prev_result = result
        except AssertionError as e:
            print(f"  [FAIL] state={state}: {e}")

    return passed, total


def diff_against_harness(spec: PaletteSpec, rom_path: Path,
                          savestate: Path) -> tuple[int, int]:
    """Run mGBA-headless on a savestate, dump CRAM, compare to oracle.
    Returns (matched, total) palette comparisons.

    The savestate establishes (FFBE, FFBF, FFC0, FFD0, FFA9). We read
    those from the live state, run oracle, then sample CRAM at a later
    frame (after the wrapper has had time to act).
    """
    import subprocess
    import tempfile

    tmp_dir = REPO_ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    cram_log = tmp_dir / "oracle_diff_cram.log"
    state_log = tmp_dir / "oracle_diff_state.log"

    lua = f'''
local frame = 0
callbacks:add("frame", function()
  frame = frame + 1
  if frame == 200 then
    -- Sample current state
    local h = io.open("{state_log}", "w")
    h:write(string.format("%02X %02X %02X %02X %02X\\n",
      emu:read8(0xFFBE), emu:read8(0xFFBF), emu:read8(0xFFC0),
      emu:read8(0xFFD0), emu:read8(0xFFA9)))
    h:close()
    -- Sample all BGP + OBP CRAM (match test_fresh_boot.py format)
    local h2 = io.open("{cram_log}", "w")
    for bgp = 0, 7 do
      h2:write(string.format("BGP%d:", bgp))
      for c = 0, 3 do
        emu:write8(0xFF68, bgp * 8 + c * 2)
        local lo = emu:read8(0xFF69)
        emu:write8(0xFF68, bgp * 8 + c * 2 + 1)
        local hi = emu:read8(0xFF69)
        h2:write(string.format(" %02X %02X", lo, hi))
      end
      h2:write("\\n")
    end
    for obp = 0, 7 do
      h2:write(string.format("OBP%d:", obp))
      for c = 0, 3 do
        emu:write8(0xFF6A, obp * 8 + c * 2)
        local lo = emu:read8(0xFF6B)
        emu:write8(0xFF6A, obp * 8 + c * 2 + 1)
        local hi = emu:read8(0xFF6B)
        h2:write(string.format(" %02X %02X", lo, hi))
      end
      h2:write("\\n")
    end
    h2:close()
    emu:stop()
  end
end)
'''
    lua_path = tmp_dir / "oracle_diff.lua"
    lua_path.write_text(lua)

    cmd = ["xvfb-run", "-a", "/home/struktured/bin/mgba-qt",
           str(rom_path), "-t", str(savestate),
           "--script", str(lua_path), "-l", "0"]
    env = {"SDL_AUDIODRIVER": "dummy"}
    try:
        subprocess.run(cmd, timeout=30, env={**__import__('os').environ, **env},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass

    if not state_log.exists() or not cram_log.exists():
        print(f"  ERROR: no output from mGBA run")
        return 0, 1

    # Parse state
    state_bytes = [int(x, 16) for x in state_log.read_text().strip().split()]
    state = GameState(
        ffbe=state_bytes[0], ffbf=state_bytes[1], ffc0=state_bytes[2],
        ffd0=state_bytes[3], ffa9=state_bytes[4],
    )
    print(f"  State at f=200: FFBE={state.ffbe:02X} FFBF={state.ffbf:02X} "
          f"FFC0={state.ffc0:02X} FFD0={state.ffd0:02X} FFA9={state.ffa9:02X}")

    # Parse CRAM
    actual_bgp: list[bytes] = []
    actual_obp: list[bytes] = []
    for line in cram_log.read_text().strip().split("\n"):
        head, rest = line.split(":", 1)
        bs = bytes(int(x, 16) for x in rest.split())
        if head.startswith("BGP"):
            actual_bgp.append(bs)
        else:
            actual_obp.append(bs)

    # Oracle: we don't have prev CRAM, so assume cache miss (palette_loader fired)
    # by setting ffa9=0xFF (impossible hash since real hashes are 1-256)
    # Actually for diff, just compare oracle's expected (full load) vs actual.
    oracle_state = GameState(ffbe=state.ffbe, ffbf=state.ffbf,
                              ffc0=state.ffc0, ffd0=state.ffd0, ffa9=0xFF)
    expected = cond_pal_oracle(oracle_state, spec)

    matched = total = 0
    print(f"  --- BGP diff (oracle vs harness) ---")
    for i in range(8):
        ok = expected.bgp[i] == actual_bgp[i]
        total += 1
        matched += ok
        if not ok:
            print(f"    BGP{i}: oracle={expected.bgp[i].hex()}  "
                  f"actual={actual_bgp[i].hex()}")
    print(f"  --- OBP diff ---")
    for i in range(8):
        ok = expected.obp[i] == actual_obp[i]
        total += 1
        matched += ok
        if not ok:
            print(f"    OBP{i}: oracle={expected.obp[i].hex()}  "
                  f"actual={actual_obp[i].hex()}")
    return matched, total


def diff_against_rom_source(spec: PaletteSpec, rom_path: Path,
                             pal_addr: int = 0x6800) -> tuple[int, int]:
    """Verify the build's bg_data + obj_data tables at pal_addr in the ROM
    exactly match what the oracle expects from the YAML.

    This is the SPEC-VS-BUILD check: did `bg_experiment.py` correctly
    serialize the YAML into the ROM's palette table? If yes, oracle's
    expected BGP0..7 / OBP0..7 should byte-match the ROM at pal_addr.

    Unlike --diff (mGBA CRAM compare), this is independent of mGBA's
    CGB color correction — we're diffing raw ROM bytes vs YAML spec.

    pal_addr default 0x6800 is from bg_experiment.py line 687
    (bank 13 base offset for bg_data; obj_data starts at pal_addr+64).
    """
    rom = rom_path.read_bytes()
    # bank 13 maps to ROM offset 13 * 0x4000 + (cpu_addr - 0x4000)
    rom_offset = 13 * 0x4000 + (pal_addr - 0x4000)
    bg_bytes = rom[rom_offset:rom_offset + 64]
    obj_bytes = rom[rom_offset + 64:rom_offset + 128]

    matched = total = 0
    print(f"  --- BG data (build vs YAML) ---")
    for i in range(8):
        rom_pal = bg_bytes[i * 8:(i + 1) * 8]
        yaml_pal = spec.bg[i]
        ok = rom_pal == yaml_pal
        total += 1
        matched += ok
        if not ok:
            print(f"    BGP{i}: yaml={yaml_pal.hex()}  rom={rom_pal.hex()}")
    print(f"  --- OBJ data (build vs YAML) ---")
    for i in range(8):
        rom_pal = obj_bytes[i * 8:(i + 1) * 8]
        yaml_pal = spec.obj[i]
        ok = rom_pal == yaml_pal
        total += 1
        matched += ok
        if not ok:
            print(f"    OBP{i}: yaml={yaml_pal.hex()}  rom={rom_pal.hex()}")
    return matched, total


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fuzz", type=int, default=0,
                   help="Run N random fuzz cases")
    p.add_argument("--diff", type=Path,
                   help="ROM path; diff oracle vs mGBA-headless CRAM "
                        "(NOTE: mGBA applies CGB color correction → "
                        "exact byte match not expected; see --rom-diff)")
    p.add_argument("--rom-diff", type=Path,
                   help="ROM path; diff oracle vs raw ROM bg_data/obj_data "
                        "tables at bank13:0x6800. This is the spec-vs-build "
                        "check independent of color correction.")
    p.add_argument("--savestate", type=Path,
                   default=REPO_ROOT / "save_states_for_claude" / "level1_sara_w_alone.ss0",
                   help="Savestate for --diff harness")
    p.add_argument("--yaml", type=Path, default=PALETTE_YAML,
                   help="Palette YAML to load")
    args = p.parse_args()

    print(f"Loading palette spec from {args.yaml}")
    spec = PaletteSpec.load(args.yaml)
    print(f"  bg palettes: {len(spec.bg)}, obj palettes: {len(spec.obj)}, "
          f"boss palettes: {len(spec.boss_pal_table)}")
    print()

    print("=== Self-test (canonical state cases) ===")
    sp, st = self_test(spec)
    print(f"  {sp}/{st} passed")
    print()

    if args.fuzz > 0:
        print(f"=== Fuzz ({args.fuzz} random states) ===")
        fp, ft = fuzz(spec, args.fuzz)
        print(f"  {fp}/{ft} passed (coherence + hash math)")
        print()

    diff_rc = 0
    if args.rom_diff:
        print(f"=== ROM-source diff: oracle vs ROM bg_data/obj_data ({args.rom_diff.name}) ===")
        rm, rt = diff_against_rom_source(spec, args.rom_diff)
        print(f"  {rm}/{rt} palette tables matched (spec → build serialization)")
        if rm < rt:
            diff_rc = 1
        print()

    if args.diff:
        print(f"=== CRAM diff: oracle vs mGBA-headless ({args.diff.name}) ===")
        print(f"  NOTE: mGBA applies CGB color correction; exact match not expected")
        print(f"  savestate: {args.savestate.name}")
        dm, dt = diff_against_harness(spec, args.diff, args.savestate)
        print(f"  {dm}/{dt} palette comparisons matched (informational; "
              f"color-correction-aware diff TODO)")
        print()

    rc = 0 if (sp == st and diff_rc == 0) else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
