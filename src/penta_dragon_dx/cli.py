import click
from . import rom_utils, palette_injector, patch_builder, injector

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
def inject(rom, palette_file, out):
    """Inject GBC palette data and init stub into ROM."""
    data = rom_utils.read_rom_bytes(rom)
    palettes = palette_injector.load_palettes(palette_file)
    
    # Build palette binary data
    bg_bytes, obj_bytes, manifest = palette_injector.build_palette_blocks(palettes)
    click.echo(f"Built palettes: {len(bg_bytes)} BG bytes, {len(obj_bytes)} OBJ bytes")
    click.echo(f"Manifest: {len(manifest['bg'])} BG palettes, {len(manifest['obj'])} OBJ palettes")
    
    # Find best free space region
    free_regions = rom_utils.find_free_space(data, min_len=128)
    if not free_regions:
        click.echo("ERROR: No suitable free space found in ROM", err=True)
        return
    
    best_region = free_regions[0]
    needed = len(bg_bytes) + len(obj_bytes) + 64  # stub code ~50 bytes + data
    if best_region["length"] < needed:
        click.echo(f"ERROR: Largest free region ({best_region['length']} bytes) too small for {needed} bytes", err=True)
        return
    
    click.echo(f"Using free space: bank {best_region['bank']} @0x{best_region['bank_addr']:04X}, {best_region['length']} bytes")
    
    # Inject palette system
    modified, info = injector.inject_palette_system(data, bg_bytes, obj_bytes, best_region["offset"])
    click.echo(f"Injected stub at file offset 0x{info['stub_offset']:06X} (GB addr 0x{info['stub_gb_addr']:04X})")
    click.echo(f"  Stub size: {info['stub_size']} bytes")
    click.echo(f"  Total injected: {info['total_size']} bytes")
    
    # Set CGB flag in header
    modified = injector.patch_cgb_flag(modified)
    click.echo("Patched CGB compatibility flag in header")
    
    rom_utils.write_rom_bytes(out, modified)
    click.echo(f"\nModified ROM written to: {out}")
    click.echo("\nNEXT STEPS:")
    click.echo(f"1. Disassemble to find init hook point (after boot, before main loop)")
    click.echo(f"2. Patch a CALL 0x{info['stub_gb_addr']:04X} instruction into init sequence")
    click.echo(f"3. Generate IPS patch with: penta-colorize build-patch --original '{rom}' --modified '{out}' --out dist/penta-dx.ips")
    click.echo(f"4. Test in SameBoy/BGB with CGB mode enabled")

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
