from typing import Any, Tuple
import yaml
from . import rom_utils

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

    The manifest maps palette names to indices and byte ranges for potential runtime switching.
    Also propagates optional `obj_palette_map` from YAML to help assign OAM palette indices per entity.
    """
    bg = bytearray()
    obj = bytearray()
    manifest: dict[str, Any] = {"bg": {}, "obj": {}, "obj_palette_map": {}}

    def pack_group(group: dict[str, Any], out: bytearray, section: str):
        idx = 0
        for name, entry in group.items():
            # Support two YAML styles:
            # 1) name: ["7FFF", "03E0", "0280", "0000"]
            # 2) name: { name: "Display Name", colors: ["7FFF", ...] }
            if isinstance(entry, dict):
                colors = entry.get("colors")
                display_name = entry.get("name", name)
            else:
                colors = entry
                display_name = name

            if not isinstance(colors, list):
                raise ValueError(f"Palette '{name}' must define a 'colors' list")
            if len(colors) != 4:
                raise ValueError(f"Palette '{name}' must have 4 colors (got {len(colors)})")

            start_byte = len(out)
            for c in colors:
                out.extend(_bgr555_hex_to_le_bytes(c))
            # Use display_name in manifest, but keep key association with original name
            manifest[section][name] = {"index": idx, "byte_offset": start_byte, "display": display_name}
            idx += 1

    if palettes.get("bg_palettes"):
        pack_group(palettes["bg_palettes"], bg, "bg")
    if palettes.get("obj_palettes"):
        pack_group(palettes["obj_palettes"], obj, "obj")
    # Optional mapping: name -> palette index (0-7)
    opm = palettes.get("obj_palette_map")
    if isinstance(opm, dict):
        # Validate indices and store verbatim
        for k, v in opm.items():
            if not isinstance(v, int) or not (0 <= v <= 7):
                raise ValueError(f"obj_palette_map for '{k}' must be int in [0,7], got {v!r}")
        manifest["obj_palette_map"] = dict(opm)
    return bytes(bg), bytes(obj), manifest


def _emit_stub(bg_bytes: bytes, obj_bytes: bytes, vblank_safe: bool = False, original_vblank_addr: int = None) -> bytes:
    """Return GBZ80 palette write stub.

    Modes:
    - Normal: simple CGB gate (RET if DMG), write palettes, RET.
    - VBlank safe: assumes invocation from VBlank vector; keeps short to limit ISR latency.
      If original_vblank_addr provided, jumps to original handler after palette writes.
    """
    code = bytearray()

    # Gate: if not CGB (KEY1 bit7 == 0) skip palettes and go to original handler
    code += bytes([0xF0, 0x4D])        # LDH A,[FF4D]
    code += bytes([0xCB, 0x7F])        # BIT 7,A
    
    if vblank_safe and original_vblank_addr:
        # On DMG, jump directly to original handler
        code += bytes([0xC2, 0x06, 0x00])  # JP NZ, +6 (skip the DMG jump)
        code += bytes([0xC3, original_vblank_addr & 0xFF, (original_vblank_addr >> 8) & 0xFF])  # JP original
    else:
        code += bytes([0xC8])              # RET Z

    # Preserve registers for ISR safety
    if vblank_safe:
        code += bytes([0xF5])  # PUSH AF

    # BG palettes
    code += bytes([0x3E, 0x80])        # LD A,0x80 (index0, auto-inc)
    code += bytes([0xE0, 0x68])        # LDH [FF68],A
    for b in bg_bytes:
        code += bytes([0x3E, b])
        code += bytes([0xE0, 0x69])

    # OBJ palettes
    code += bytes([0x3E, 0x80])
    code += bytes([0xE0, 0x6A])
    for b in obj_bytes:
        code += bytes([0x3E, b])
        code += bytes([0xE0, 0x6B])

    if vblank_safe:
        code += bytes([0xF1])  # POP AF

    if not vblank_safe:
        # Tracer only in non-ISR mode to reduce interrupt time
        code += bytes([0x3E, 0x42])
        code += bytes([0x21, 0x00, 0xC0])
        code += bytes([0x77])

    # If VBlank ISR mode, jump to original handler instead of RET
    if vblank_safe and original_vblank_addr:
        code += bytes([0xC3, original_vblank_addr & 0xFF, (original_vblank_addr >> 8) & 0xFF])  # JP original
    else:
        code += bytes([0xC9])    # RET
        
    return bytes(code)


def apply_palettes(rom: bytes, palettes: dict[str, Any], hook_offset: int | None = None, multi_patch: bool = True, max_hooks: int = 16, vblank_hook: bool = False, boot_hook: bool = False, late_init_hook: bool = False):
    # Build binary blocks
    bg_bytes, obj_bytes, manifest = build_palette_blocks(palettes)

    total_needed = len(bg_bytes) + len(obj_bytes) + 128  # include stub headroom (larger for VBlank stub)
    free = rom_utils.find_free_space(rom, min_len=max(64, total_needed))
    if not free:
        raise RuntimeError("No sufficient free-space region found for palette data.")
    
    # For VBlank/boot hook, we MUST use bank 0 (always accessible during interrupts/boot)
    region = None
    if vblank_hook or boot_hook:
        bank0_regions = [r for r in free if r["bank"] == 0 and r["length"] >= total_needed]
        if not bank0_regions:
            # If no space in bank 0, we can use any bank for boot hook (not interrupt-safe but runs once)
            if boot_hook and not vblank_hook:
                region = free[0]  # Use largest available
            else:
                raise RuntimeError("VBlank hook requires free space in bank 0, but none found.")
        else:
            region = bank0_regions[0]
    elif late_init_hook:
        # Late init runs after system is stable, can use any bank
        region = free[0]
    else:
        # Prefer bank 0 (fixed, always mapped) for safe hooking
        bank0_regions = [r for r in free if r["bank"] == 0 and r["length"] >= total_needed]
        if bank0_regions:
            region = bank0_regions[0]
        elif hook_offset is not None:
            hook_bank = hook_offset // 0x4000
            same_bank = [r for r in free if r["bank"] == hook_bank and r["length"] >= total_needed]
            region = (same_bank[0] if same_bank else None)
        if region is None:
            # Fallback to largest region
            region = free[0]
    
    start = region["offset"]

    rom_mut = bytearray(rom)

    # Initialize modifications list
    modifications = []

    # Optional: Late init hook (0x015F - after LCD init, before main loop)
    if late_init_hook:
        # Hook at 0x015F: CALL 0x3B77 (first main loop call)
        # We need a trampoline since our stub is in bank 13 but bank 1 is loaded
        
        original_bytes = rom_mut[0x015F:0x0162]  # CD 77 3B
        original_call_addr = original_bytes[1] | (original_bytes[2] << 8)
        
        # Place main stub in bank 13
        stub = _emit_stub(bg_bytes, obj_bytes, vblank_safe=False)
        stub_off = start
        stub_bank = region["bank"]
        rom_mut[stub_off : stub_off + len(stub)] = stub
        
        # Build trampoline code that handles bank switching
        trampoline = bytearray()
        
        # Save AF and current bank
        trampoline += bytes([0xF5])  # PUSH AF
        trampoline += bytes([0x3E, stub_bank])  # LD A, bank_num
        trampoline += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A (MBC1 bank select)
        
        # Call palette stub
        stub_call_addr = 0x4000 + (stub_off % 0x4000)  # Address in switchable bank
        trampoline += bytes([0xCD, stub_call_addr & 0xFF, (stub_call_addr >> 8) & 0xFF])
        
        # Restore bank 1
        trampoline += bytes([0x3E, 0x01])  # LD A, 1
        trampoline += bytes([0xEA, 0x00, 0x20])  # LD [0x2000], A
        trampoline += bytes([0xF1])  # POP AF
        
        # Call original function
        trampoline += bytes([0xCD, original_call_addr & 0xFF, (original_call_addr >> 8) & 0xFF])
        trampoline += bytes([0xC9])  # RET
        
        # Find space for trampoline in bank 0
        trampoline_placed = False
        for addr in range(0x200, 0x4000 - len(trampoline)):
            if all(rom_mut[addr + i] in [0x00, 0xFF] for i in range(len(trampoline))):
                rom_mut[addr:addr + len(trampoline)] = trampoline
                trampoline_addr = addr
                trampoline_placed = True
                break
        
        if not trampoline_placed:
            raise RuntimeError(f"Could not find {len(trampoline)} bytes for trampoline in bank 0")
        
        # Patch the CALL at 0x015F to point to trampoline
        call_bytes = bytes([0xCD, trampoline_addr & 0xFF, (trampoline_addr >> 8) & 0xFF])
        rom_mut[0x015F:0x0162] = call_bytes
        
        modifications.append({
            "type": "late-init-hook",
            "stub_addr": stub_call_addr,
            "stub_offset": stub_off,
            "stub_bank": stub_bank,
            "trampoline_addr": hex(trampoline_addr),
            "trampoline_size": len(trampoline),
            "original_call": hex(original_call_addr),
            "hook_location": "0x015F",
        })
    # Optional: Boot entry point hook (0x0100)
    elif boot_hook:
        # Read original boot entry - typically: NOP; JP xxxx or just JP xxxx
        original_bytes = rom_mut[0x100:0x104]
        
        # Extract entry point address
        if original_bytes[0] == 0x00 and original_bytes[1] == 0xC3:  # NOP; JP xxxx
            original_entry_addr = original_bytes[2] | (original_bytes[3] << 8)
            patch_at = 0x100
        elif original_bytes[0] == 0xC3:  # JP xxxx
            original_entry_addr = original_bytes[1] | (original_bytes[2] << 8)
            patch_at = 0x100
        else:
            # Fallback: code starts at 0x150
            original_entry_addr = 0x0150
            patch_at = 0x100
        
        # Place stub that runs once then jumps to game
        stub = _emit_stub(bg_bytes, obj_bytes, vblank_safe=False, original_vblank_addr=original_entry_addr)
        stub_off = start
        stub_addr_bank = stub_off if region["bank"] == 0 else 0x4000 + (stub_off % 0x4000)
        rom_mut[stub_off : stub_off + len(stub)] = stub
        
        # Patch boot entry to JP to our stub
        call_addr = stub_addr_bank
        # Use NOP + JP for compatibility (entry point is 4 bytes: 0x100-0x103)
        boot_patch = bytes([0x00, 0xC3, call_addr & 0xFF, (call_addr >> 8) & 0xFF])
        rom_mut[patch_at:patch_at + 4] = boot_patch
        
        modifications.append({
            "type": "boot-hook",
            "stub_addr": call_addr,
            "stub_offset": stub_off,
            "stub_bank": region["bank"],
            "original_entry": hex(original_entry_addr),
            "original_bytes": original_bytes[:4].hex(),
        })
    # Optional: VBlank vector hook (interrupt 0x0040)
    elif vblank_hook:
        # Read original VBlank handler - should be JP xxxx (C3 xx xx)
        original_bytes = rom_mut[0x40:0x43]
        
        # Extract target address from JP instruction
        if original_bytes[0] == 0xC3:  # JP instruction
            original_handler_addr = original_bytes[1] | (original_bytes[2] << 8)
        else:
            # Fallback: assume code starts at 0x43
            original_handler_addr = 0x0043
        
        # Place stub with embedded palette data that jumps to original handler
        stub = _emit_stub(bg_bytes, obj_bytes, vblank_safe=True, original_vblank_addr=original_handler_addr)
        stub_off = start
        stub_addr_bank = stub_off if region["bank"] == 0 else 0x4000 + (stub_off % 0x4000)
        rom_mut[stub_off : stub_off + len(stub)] = stub
        
        # Patch VBlank vector to JP to our stub
        call_addr = stub_addr_bank
        jp_bytes = bytes([0xC3, call_addr & 0xFF, (call_addr >> 8) & 0xFF])  # JP stub
        rom_mut[0x40:0x43] = jp_bytes
        
        modifications.append({
            "type": "vblank-hook",
            "stub_addr": call_addr,
            "stub_offset": stub_off,
            "stub_bank": region["bank"],
            "original_handler": hex(original_handler_addr),
            "original_bytes": original_bytes.hex(),
        })
    else:
        # Normal mode: simple stub without original handler
        stub = _emit_stub(bg_bytes, obj_bytes, vblank_safe=False)
        stub_off = start
        stub_addr_bank = stub_off if region["bank"] == 0 else 0x4000 + (stub_off % 0x4000)
        rom_mut[stub_off : stub_off + len(stub)] = stub

    # Add palette injection metadata
    modifications.append({
        "type": "inject-palettes",
        "region": {
            "offset": start,
            "length": region["length"],
            "bank": region["bank"],
            "bank_addr": region["bank_addr"],
        },
        "bg_block": {"offset": stub_off, "length": len(bg_bytes)},
        "obj_block": {"offset": stub_off, "length": len(obj_bytes)},
        "manifest": manifest,
    })

    # Multi-patch hooks if not using VBlank vector
    if not vblank_hook and hook_offset is not None:
        hook_bank = hook_offset // 0x4000
        
        # Patch CALLs into safe NOP runs in the target bank
        call_addr = stub_addr_bank
        call_bytes = bytes([0xCD, call_addr & 0xFF, (call_addr >> 8) & 0xFF])
        
        # Only patch within the hook bank to ensure bank safety
        nop_runs = rom_utils.find_nop_runs_in_bank(rom_mut, hook_bank, min_len=3)
        selected = []
        for r in nop_runs:
            if r["offset"] >= hook_offset:
                selected.append(r)
                if len(selected) >= max_hooks:
                    break
        if not selected and nop_runs:
            selected = nop_runs[:max_hooks]
        
        for r in selected:
            off = r["offset"]
            rom_mut[off : off + 3] = call_bytes
            modifications.append({
                "type": "hook-stub",
                "hook_offset": off,
                "stub_offset": stub_off,
                "stub_addr": stub_addr_bank,
                "stub_bank": hook_bank,
            })

    return bytes(rom_mut), modifications
