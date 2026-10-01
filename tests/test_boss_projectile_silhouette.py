"""Issue #15: native projectiles must not excuse detached/corrupt boss art."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import verify_boss_silhouette_offline as oracle


class ProjectileSilhouetteTests(unittest.TestCase):
    def setUp(self):
        self.contract = oracle.load_contract(oracle.DEFAULT_CONTRACTS, "penta_dragon")
        self.image = Image.new("RGB", (160, 144), (0, 0, 0))
        ImageDraw.Draw(self.image).rectangle((24, 8, 115, 79), fill=(220, 20, 20))
        oam = bytearray(160)
        oam[16:20] = bytes((36, 148, 0x4F, 0))
        self.evidence = dict(schema="penta-projectile-phase-v1", frame=30,
                             cgb=True, lcdc=0x93, oam=oam.hex(),
                             tile0=oracle.PENTA_PROJECTILE_CHR.hex(), tile1="00" * 16,
                             obj_cram=(bytes.fromhex("0000e0030002ff03") + bytes(56)).hex())
        self.pixels = oracle.native_projectile_pixels(self.evidence)[0]["pixels"]
        for point, color in self.pixels.items():
            self.image.putpixel(point, color)

    def result(self, evidence=None):
        return oracle.analyze_penta(self.image, self.contract,
                                    self.evidence if evidence is None else evidence)

    def test_exact_native_projectile_is_classified_without_editing_image(self):
        before = self.image.tobytes()
        row = self.result()
        self.assertEqual(row["raw_detached_fragments"], 1)
        self.assertEqual(row["detached_fragments"], 0)
        self.assertEqual(row["native_projectile_components"][0]["oam_slots"], [4])
        self.assertEqual(self.image.tobytes(), before)

    def test_no_evidence_means_no_exemption(self):
        self.assertEqual(oracle.analyze_penta(self.image, self.contract)["status"], "fail")

    def test_unknown_sprite_tile_is_not_exempt(self):
        evidence = copy.deepcopy(self.evidence)
        oam = bytearray.fromhex(evidence["oam"])
        oam[18] = 0x4E
        evidence["oam"] = oam.hex()
        self.assertEqual(self.result(evidence)["status"], "fail")

    def test_wrong_position_is_not_exempt(self):
        evidence = copy.deepcopy(self.evidence)
        oam = bytearray.fromhex(evidence["oam"])
        oam[17] += 1
        evidence["oam"] = oam.hex()
        self.assertEqual(self.result(evidence)["status"], "fail")

    def test_unknown_chr_is_not_exempt(self):
        evidence = dict(self.evidence, tile0="01" + self.evidence["tile0"][2:])
        self.assertEqual(self.result(evidence)["status"], "fail")

    def test_wrong_vram_bank_is_not_exempt(self):
        evidence = copy.deepcopy(self.evidence)
        oam = bytearray.fromhex(evidence["oam"])
        oam[19] |= 8
        evidence["oam"] = oam.hex()
        self.assertEqual(self.result(evidence)["status"], "fail")

    def test_missing_and_wrong_color_pixels_fail(self):
        point = next(iter(self.pixels))
        for color in ((0, 0, 0), (255, 0, 255)):
            with self.subTest(color=color):
                self.image.putpixel(point, color)
                self.assertEqual(self.result()["status"], "fail")

    def test_copied_boss_art_still_fails(self):
        ImageDraw.Draw(self.image).rectangle((5, 100, 10, 105), fill=(220, 20, 20))
        row = self.result()
        self.assertEqual(row["raw_detached_fragments"], 2)
        self.assertEqual(row["detached_fragments"], 1)
        self.assertEqual(row["status"], "fail")

    def test_truncated_receipt_is_rejected(self):
        for field in ("oam", "obj_cram", "tile0", "tile1"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.result(dict(self.evidence, **{field: ""}))

    def test_unsupported_modes_receive_no_exemption(self):
        for update in ({"cgb": False}, {"lcdc": 0x97}, {"lcdc": 0x91}):
            with self.subTest(update=update):
                self.assertEqual(self.result(dict(self.evidence, **update))["status"], "fail")

    def test_sprite_flips_are_decoded(self):
        for attr in (0x20, 0x40, 0x60):
            evidence = copy.deepcopy(self.evidence)
            oam = bytearray.fromhex(evidence["oam"])
            oam[19] = attr
            evidence["oam"] = oam.hex()
            expected = oracle.native_projectile_pixels(evidence)[0]["pixels"]
            for point, color in self.pixels.items():
                dx, dy = point[0] - 140, point[1] - 20
                flipped = (140 + (7 - dx if attr & 32 else dx),
                           20 + (7 - dy if attr & 64 else dy))
                self.assertEqual(expected[flipped], color)

    def test_stale_image_binding_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            path = Path(directory) / "phase.png"
            self.image.save(path)
            sidecar = Path(f"{path}.sprites.json")
            payload = dict(self.evidence, image_sha256="0" * 64)
            sidecar.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                oracle.analyze_image(path, "penta_dragon", oracle.DEFAULT_CONTRACTS)
            payload["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            sidecar.write_text(json.dumps(payload))
            self.assertEqual(oracle.analyze_image(path, "penta_dragon", oracle.DEFAULT_CONTRACTS)["status"], "pass")

    def test_missing_gallery_image_fails_cleanly(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            result = oracle.analyze_gallery(Path(directory), 120, oracle.DEFAULT_CONTRACTS)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(result["failures"])


if __name__ == "__main__":
    unittest.main()
