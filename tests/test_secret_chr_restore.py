"""Structural guards for issue #23; emulator acceptance is a separate test."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/'scripts/diagnostics/build_secret_chr_restore.py'
SPEC=importlib.util.spec_from_file_location('secret_chr_restore',PATH)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class SecretChrRestoreTests(unittest.TestCase):
    def setUp(self):
        parent=bytearray(b'\xff'*0x80000)
        parent[0x147:0x149]=bytes([0x1B,4])
        parent[0xCC5:0xCC5+len(mod.LOADER)]=mod.LOADER
        parent[0x9BE:0x9C4]=bytes.fromhex('E0 99 EA 00 21 C9')
        parent[0xCD5:0xCE1]=bytes(range(0x74,0x80))
        self.parent=bytes(parent)
        self.stock=bytes(range(256))*1024
        # Synthetic fixtures test the delta without distributing game assets.
        self.pins=patch.multiple(mod,PARENT_SHA=mod.digest(self.parent),STOCK_SHA=mod.digest(self.stock))
        self.pins.start();self.addCleanup(self.pins.stop)

    def test_preserves_parent_except_loader_and_checksums(self):
        result=mod.build(self.parent,self.stock)
        changes={i for i,(a,b) in enumerate(zip(self.parent,result)) if a!=b}
        self.assertLessEqual(changes,{0xCC7,0x148,0x14D,0x14E,0x14F})
        self.assertEqual(result[0xCC7],32)
        self.assertEqual(result[0x34000:0x38000],self.parent[0x34000:0x38000])

    def test_stock_asset_bank_and_expansion_padding(self):
        result=mod.build(self.parent,self.stock)
        self.assertEqual(len(result),0x100000)
        self.assertEqual(result[0x80000:0x84000],self.stock[0x34000:0x38000])
        self.assertEqual(result[0x84000:],b'\xff'*0x7C000)
        self.assertEqual(result[0x83400:0x84000],self.stock[0x37400:0x38000])

    def test_header_and_global_checksum(self):
        result=mod.build(self.parent,self.stock)
        self.assertEqual(result[0x148],5)
        self.assertEqual(result[0x14D],(-sum(result[0x134:0x14D])-25)&255)
        self.assertEqual(int.from_bytes(result[0x14E:0x150],'big'),(sum(result[:0x14E])+sum(result[0x150:]))&65535)

    def test_rejects_unknown_parent(self):
        with self.assertRaises(ValueError):mod.build(self.parent[:-1]+b'\0',self.stock)

    def test_rejects_changed_loader_even_with_updated_pin(self):
        parent=bytearray(self.parent);parent[0xCC6]=0
        with patch.object(mod,'PARENT_SHA',mod.digest(parent)):
            with self.assertRaises(ValueError):mod.build(bytes(parent),self.stock)


if __name__=='__main__':unittest.main()
