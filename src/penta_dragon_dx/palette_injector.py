from typing import Any, Tuple
import yaml

# GBC palette entries: 4 colors each, each color 15-bit (BGR555). We'll store as hex strings for now.
# YAML structure example:
# bg_palettes:
#   HUD: ["7FFF", "4210", "2108", "0000"]
# obj_palettes:
#   Player: ["7C1F", "3C0F", "1C07", "0000"]


def load_palettes(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _bgr555_hex_to_le_bytes(h: str) -> bytes:
    h = h.strip().upper()
    if len(h) != 4 or any(c not in "0123456789ABCDEF" for c in h):
        raise ValueError(f"Invalid BGR555 color '{h}', expected 4 hex digits (e.g. '7FFF')")
    val = int(h, 16) & 0x7FFF
    return val.to_bytes(2, "little")


def build_palette_blocks(palettes: dict[str, Any]) -> Tuple[bytes, bytes, dict]:
    """Return (bg_bytes, obj_bytes, manifest) where bytes are LE BGR555 stream for GBC registers.

    The manifest maps palette names to index ranges for potential runtime switching.
    """
    bg = bytearray()
    obj = bytearray()
    manifest: dict[str, Any] = {"bg": {}, "obj": {}}

    def pack_group(group: dict[str, list[str]], out: bytearray, section: str):
        idx = 0
        for name, colors in group.items():
            if len(colors) != 4:
                raise ValueError(f"Palette '{name}' must have 4 colors (got {len(colors)})")
            start_byte = len(out)
            for c in colors:
                out.extend(_bgr555_hex_to_le_bytes(c))
            manifest[section][name] = {"index": idx, "byte_offset": start_byte}
            idx += 1

    if palettes.get("bg_palettes"):
        pack_group(palettes["bg_palettes"], bg, "bg")
    if palettes.get("obj_palettes"):
        pack_group(palettes["obj_palettes"], obj, "obj")
    return bytes(bg), bytes(obj), manifest


def apply_palettes(rom: bytes, palettes: dict[str, Any]):
    # Prepare binary blocks but do not inject yet.
    bg_bytes, obj_bytes, manifest = build_palette_blocks(palettes)
    modifications = [
        {"type": "prepare", "bg_bytes": len(bg_bytes), "obj_bytes": len(obj_bytes), "palettes": manifest}
    ]
    # Future: allocate free space, write palette data block, patch jump to init routine.
    return rom, modifications
