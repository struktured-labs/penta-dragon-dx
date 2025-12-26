import click
from pathlib import Path
import subprocess
import shutil
from . import rom_utils, palette_injector, patch_builder, display_patcher

@click.group()
def main():
    """Penta Dragon DX colorization toolkit."""
    pass

@main.command()
@click.option("--rom", type=click.Path(exists=True, dir_okay=False), required=True, help="Path to original ROM")
def verify(rom):
    info = rom_utils.inspect_rom(rom)
    click.echo(f"Size: {info['size']} bytes")
    click.echo(f"CRC32: {info['crc32']:08X}")
    if info.get("warning"):
        click.echo(f"Warning: {info['warning']}")
    hdr = info.get("header")
    if hdr:
        click.echo("Header:")
        click.echo(f"  Title: {hdr['title']}")
        click.echo(f"  CGB: {hdr['cgb_support']} (flag=0x{hdr['cgb_flag']:02X})")
        click.echo(f"  Cart: {hdr['cartridge_type_name']} (0x{hdr['cartridge_type']:02X})")
        if hdr.get("rom_size_expected"):
            click.echo(f"  Declared ROM size: {hdr['rom_size_expected']} bytes (code 0x{hdr['rom_size_code']:02X})")
        if hdr.get("ram_size_expected") is not None:
            click.echo(f"  Declared RAM size: {hdr['ram_size_expected']} bytes (code 0x{hdr['ram_size_code']:02X})")
        click.echo(f"  Header checksum: calc=0x{hdr['header_checksum_calc']:02X}, stored=0x{hdr['header_checksum']:02X}")
        click.echo(f"  Global checksum: calc=0x{hdr['global_checksum_calc']:04X}, stored=0x{hdr['global_checksum']:04X}")

@main.command()
@click.option("--rom", type=click.Path(exists=True), required=True)
@click.option("--palette-file", type=click.Path(exists=True), required=True)
@click.option("--out", type=click.Path(dir_okay=False), required=True, help="Output modified ROM copy")
@click.option("--hook-offset", type=str, default=None, help="File offset (hex like 0x1234 or dec) to patch CALL to stub")
@click.option("--vblank", is_flag=True, help="Hook stub into VBlank interrupt vector (0x0040) instead of code offset")
@click.option("--boot", is_flag=True, help="Hook stub into boot entry point (0x0100) - runs once at startup")
@click.option("--late-init", is_flag=True, help="Hook after LCD init, before main loop (0x015F) - most compatible")
@click.option("--fix-display", is_flag=True, default=True, help="Apply CGB display compatibility patches (default: enabled)")
def inject(rom, palette_file, out, hook_offset, vblank, boot, late_init, fix_display):
    """Inject GBC palette data and optional init stub into ROM."""
    data = rom_utils.read_rom_bytes(rom)
    
    # Apply display compatibility patches first if requested
    if fix_display:
        click.echo("Applying CGB display compatibility patches...")
        data, display_patches = display_patcher.apply_all_display_patches(data)
        for addr, orig, patched in display_patches:
            click.echo(f"  Patched @0x{addr:04X}: {len(patched)} bytes")
    palettes = palette_injector.load_palettes(palette_file)
    hook = None
    if hook_offset:
        try:
            hook = int(hook_offset, 0)
        except ValueError:
            raise click.BadParameter("hook-offset must be a number (e.g., 0x1234 or 4660)")
    modified, modifications = palette_injector.apply_palettes(data, palettes, hook_offset=(None if (vblank or boot or late_init) else hook), vblank_hook=vblank, boot_hook=boot, late_init_hook=late_init)
    # Ensure CGB support flag is set so emulator runs in color mode
    modified = rom_utils.set_cgb_supported(modified)
    rom_utils.write_rom_bytes(out, modified)
    click.echo(f"Wrote modified ROM → {out}")
    for m in modifications:
        if m["type"] == "inject-palettes":
            r = m["region"]
            click.echo(
                f"Palette data in bank {r['bank']:02d} @0x{r['bank_addr']:04X} (file 0x{r['offset']:06X}), bg={m['bg_block']['length']} obj={m['obj_block']['length']}"
            )
        if m["type"] == "hook-stub":
            click.echo(
                f"Patched CALL at file 0x{m['hook_offset']:06X} to stub bank {m['stub_bank']:02d} @0x{m['stub_addr']:04X}"
            )

@main.command("build-patch")
@click.option("--original", type=click.Path(exists=True), required=True)
@click.option("--modified", type=click.Path(exists=True), required=True)
@click.option("--out", type=click.Path(dir_okay=False), required=True)
def build_patch(original, modified, out):
    orig = rom_utils.read_rom_bytes(original)
    mod = rom_utils.read_rom_bytes(modified)
    patch_bytes = patch_builder.build_ips_patch(orig, mod)
    with open(out, "wb") as f:
        f.write(patch_bytes)
    click.echo(f"IPS patch written: {out} ({len(patch_bytes)} bytes)")

if __name__ == "__main__":
    main()

@main.command()
@click.option("--rom", type=click.Path(exists=True, dir_okay=False), required=True, help="Path to original ROM")
@click.option("--free-min", type=int, default=128, help="Minimum free-space run length to report")
def analyze(rom, free_min):
    """Print ROM header, free space regions, and palette write candidates."""
    data = rom_utils.read_rom_bytes(rom)
    hdr = rom_utils.parse_header(data)
    click.echo("Header summary:")
    click.echo(f"  Title: {hdr['title']}")
    click.echo(f"  CGB: {hdr['cgb_support']} (flag=0x{hdr['cgb_flag']:02X})")
    click.echo(f"  Cart: {hdr['cartridge_type_name']} (0x{hdr['cartridge_type']:02X})")
    if hdr.get("rom_size_expected"):
        click.echo(f"  Declared ROM size: {hdr['rom_size_expected']} bytes (code 0x{hdr['rom_size_code']:02X})")
    if hdr.get("ram_size_expected") is not None:
        click.echo(f"  Declared RAM size: {hdr['ram_size_expected']} bytes (code 0x{hdr['ram_size_code']:02X})")
    click.echo(f"  Header checksum: calc=0x{hdr['header_checksum_calc']:02X}, stored=0x{hdr['header_checksum']:02X}")
    click.echo(f"  Global checksum: calc=0x{hdr['global_checksum_calc']:04X}, stored=0x{hdr['global_checksum']:04X}")

    free_regions = rom_utils.find_free_space(data, min_len=free_min)
    click.echo(f"\nFree-space regions (min {free_min} bytes), top 10 by length:")
    for r in free_regions[:10]:
        click.echo(
            f"  bank {r['bank']:02d} @0x{r['bank_addr']:04X} (file 0x{r['offset']:06X}), len={r['length']} pad=0x{r['pad']:02X}"
        )

    hooks = rom_utils.find_palette_hook_candidates(data)
    click.echo(f"\nPalette write hook byte-pattern candidates: {len(hooks)} occurrences")
    if hooks[:10]:
        click.echo("  First few offsets:")
        for off in hooks[:10]:
            bank = off // 0x4000
            bank_addr = 0x4000 + (off % 0x4000) if off >= 0x4000 else off
            click.echo(f"    bank {bank:02d} @0x{bank_addr:04X} (file 0x{off:06X})")

@main.command("dev-loop")
@click.option("--rom", type=click.Path(exists=True, dir_okay=False), required=True, help="Path to original ROM")
@click.option("--palette-file", type=click.Path(exists=True), required=True)
@click.option("--hook-offset", type=str, required=False, help="File offset to patch CALL to stub (hex like 0x4000); ignored if --vblank")
@click.option("--emu", type=str, default="mgba-qt", help="Emulator command (mgba-qt, sameboy, etc.)")
@click.option("--vblank", is_flag=True, help="Use VBlank interrupt hook instead of code offset")
def dev_loop(rom, palette_file, hook_offset, emu, vblank):
    """Inject palettes and stub, write working ROM, then launch emulator."""
    hook = None
    if not vblank:
        if not hook_offset:
            raise click.BadParameter("hook-offset required unless --vblank specified")
        try:
            hook = int(hook_offset, 0)
        except ValueError:
            raise click.BadParameter("hook-offset must be numeric (e.g., 0x4000)")

    out_path = Path("rom/working/penta_dx.gb")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = rom_utils.read_rom_bytes(rom)
    palettes = palette_injector.load_palettes(palette_file)
    modified, modifications = palette_injector.apply_palettes(data, palettes, hook_offset=hook, vblank_hook=vblank)
    # Ensure CGB support flag is set so emulator runs in color mode
    modified = rom_utils.set_cgb_supported(modified)
    rom_utils.write_rom_bytes(out_path, modified)
    click.echo(f"Wrote modified ROM → {out_path}")
    for m in modifications:
        if m["type"] == "inject-palettes":
            r = m["region"]
            click.echo(
                f"Palette data in bank {r['bank']:02d} @0x{r['bank_addr']:04X} (file 0x{r['offset']:06X}), bg={m['bg_block']['length']} obj={m['obj_block']['length']}"
            )
        if m["type"] == "hook-stub":
            click.echo(
                f"Patched CALL at file 0x{m['hook_offset']:06X} to stub bank {m['stub_bank']:02d} @0x{m['stub_addr']:04X}"
            )

    cmd = shutil.which(emu) or emu
    try:
        subprocess.Popen([cmd, str(out_path)])
        click.echo(f"Launched {emu} {out_path}")
    except Exception as e:
        raise click.ClickException(f"Failed to launch emulator '{emu}': {e}")
