"""Replay an existing JSONL recording in PyBoy and dump a RICHER state per frame.

Solves: when state vector schema changes, we shouldn't ask the user to replay.
We have their input sequence — replay deterministically to extract any byte.

Input: existing JSONL with at least `f` and `keys` fields.
Output: enriched JSONL with full WRAM (C000-DFFF, 8KB) + HRAM (FF80-FFFE) +
all current PentaEnv state fields.
"""
from __future__ import annotations
import json, sys, os
from pyboy import PyBoy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


# Title nav schedule — must match play_record.lua exactly
TITLE_NAV = [
    (180, 185, "down"),
    (193, 198, "a"),
    (241, 246, "a"),
    (291, 296, "a"),
    (341, 346, "start"),
    (391, 396, "a"),
]
TITLE_END = 500


# PyBoy button names ↔ GB joypad bitmask (matches FF93 layout: ABSelStart/RLUD)
KEYMASK = {"a": 0x01, "b": 0x02, "select": 0x04, "start": 0x08,
           "right": 0x10, "left": 0x20, "up": 0x40, "down": 0x80}
MASK2BTN = {v: k for k, v in KEYMASK.items()}


def keys_to_buttons(k: int) -> list[str]:
    """Decompose joypad bitmask into list of PyBoy button names."""
    out = []
    for mask, name in MASK2BTN.items():
        if k & mask: out.append(name)
    return out


def replay(input_jsonl: str, output_jsonl: str, rom: str = ROM):
    # Load input rows (need f, keys, action)
    rows = []
    with open(input_jsonl) as f:
        for line in f:
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: pass
    print(f"Loaded {len(rows)} input rows from {input_jsonl}")
    if not rows: return

    # Build a frame→keys lookup from the recording (frame_skip=4 so keys held for 4 frames)
    keys_by_frame = {}  # exact frame → keys mask. Recording was every 4 frames.
    for r in rows:
        keys_by_frame[r["f"]] = r["keys"]
    rec_frames = sorted(keys_by_frame.keys())
    last_rec_frame = rec_frames[-1] if rec_frames else 0
    print(f"Recording spans frames {rec_frames[0]} .. {last_rec_frame}")

    pb = PyBoy(rom, window="null", sound_emulated=False, cgb=True)

    out = open(output_jsonl, "w")
    written = 0

    held = []
    last_recorded_keys = 0
    cur_keys_mask = 0

    f = 0
    next_rec_idx = 0
    while f <= last_rec_frame + 50:  # buffer past last frame
        f += 1

        # Determine target keys for this frame
        if f <= TITLE_END:
            # Title-nav phase
            target_btn = None
            for fr_lo, fr_hi, btn in TITLE_NAV:
                if fr_lo <= f <= fr_hi:
                    target_btn = btn; break
            target_buttons = [target_btn] if target_btn else []
        else:
            # Find the most recent recorded keys for this frame
            # Recording sampled every 4 frames; assume keys persisted between samples
            # Find largest recorded frame <= f
            while next_rec_idx + 1 < len(rec_frames) and rec_frames[next_rec_idx + 1] <= f:
                next_rec_idx += 1
            if next_rec_idx < len(rec_frames) and rec_frames[next_rec_idx] <= f:
                cur_keys_mask = keys_by_frame[rec_frames[next_rec_idx]]
            target_buttons = keys_to_buttons(cur_keys_mask)

        # Apply input: release prev held that aren't in new, press new not in prev
        new_set = set(target_buttons)
        prev_set = set(held)
        for b in prev_set - new_set:
            pb.button_release(b)
        for b in new_set - prev_set:
            pb.button_press(b)
        held = list(new_set)

        pb.tick()

        # Capture state at the recorded sample frames (every 4)
        if f in keys_by_frame:
            mem = pb.memory
            wram = bytes(mem[a] for a in range(0xC000, 0xE000))
            hram = bytes(mem[a] for a in range(0xFF80, 0xFFFF))
            oam = bytes(mem[a] for a in range(0xFE00, 0xFEA0))
            row = {
                "f": f,
                "keys": cur_keys_mask if f > TITLE_END else 0,
                "wram_C000_DFFF": wram.hex(),
                "hram_FF80_FFFE": hram.hex(),
                "oam_FE00_FE9F": oam.hex(),
            }
            # Carry forward useful single-byte fields for backward-compat
            for name, addr in [
                ("D880", 0xD880), ("FFBA", 0xFFBA), ("FFBD", 0xFFBD),
                ("FFBE", 0xFFBE), ("FFBF", 0xFFBF), ("FFC0", 0xFFC0),
                ("FFC1", 0xFFC1), ("DCBB", 0xDCBB), ("DCDC", 0xDCDC),
                ("DCDD", 0xDCDD), ("DCB8", 0xDCB8), ("DC04", 0xDC04),
                ("FFAC", 0xFFAC), ("FFAD", 0xFFAD), ("FFCF", 0xFFCF),
                ("SCY", 0xFF42), ("SCX", 0xFF43),
            ]:
                row[name] = mem[addr]
            # Carry over original action label
            for orig in rows:
                if orig["f"] == f:
                    row["action"] = orig.get("action", 0)
                    break
            out.write(json.dumps(row) + "\n")
            written += 1
            if written % 500 == 0:
                print(f"  f={f} written={written}")

    out.close()
    pb.stop()
    print(f"Done: {written} rows → {output_jsonl}")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_human.jsonl"
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".jsonl", "_enriched.jsonl")
    replay(src, dst)
