"""Identity retargeting must never repair game state to make a test pass."""
from pathlib import Path
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import normalize_mgba_state_pc as state


class LiveFixtureIdentity(unittest.TestCase):
    def test_only_crc_and_cgb_flag_change_and_invalid_sources_fail(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            source, target, rom = root / "source.ss0", root / "target.ss0", root / "rom.gb"
            raw = bytearray((i * 37 + 11) & 255 for i in range(state.GB_STATE_SIZE))
            raw[:4] = state.GB_STATE_MAGIC.to_bytes(4, "little")
            raw[state.GB_STATE_MODEL] = state.GB_MODEL_CGB
            raw[state.GB_STATE_IO + state.GB_REG_BANK] = 1
            raw[16:32] = b"PENTA DRAGON".ljust(15, b" ") + b"\x80"
            image = bytearray(0x8000)
            image[0x134:0x144] = raw[16:31] + b"\xc0"
            rom.write_bytes(image)

            def write(payload):
                state.write_png(source, [(b"gbAs", zlib.compress(payload)), (b"IEND", b"")])

            write(raw)
            state.retarget_rom_identity(source, target, rom)
            after = zlib.decompress(dict(state.png_chunks(target.read_bytes()))[b"gbAs"])
            differences = {i for i, pair in enumerate(zip(raw, after, strict=True)) if pair[0] != pair[1]}
            self.assertLessEqual(differences, {4, 5, 6, 7, 31})
            self.assertIn(31, differences)
            self.assertEqual(int.from_bytes(after[4:8], "little"), zlib.crc32(image))
            for offset, value in ((31, 0xC0), (16, 0), (8, 0), (0x350, 0xFF)):
                with self.subTest(offset=offset):
                    invalid = bytearray(raw)
                    invalid[offset] = value
                    write(invalid)
                    with self.assertRaises(ValueError):
                        state.retarget_rom_identity(source, target, rom)
