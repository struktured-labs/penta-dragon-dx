import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),
              str(Path(__file__).resolve().parents[1]/'scripts/diagnostics')]
from diagnostics import playtest_successor_lineage as lineage
from diagnostics import build_enemy_projectile_palette as builder
import verify_gameplay_obj_palettes as obj
import verify_stage1_no_bleed as bg
import playtest_successor_lineage as bg_lineage
import verify_menu_icon_palettes as menu
import menu_commit_protocol as protocol
import verify_stage1_pickup_art as art
import verify_pickup_live_palettes as pickups
import verify_stage1_spike_palettes as hazards
import verify_stage1_tilemap_copy as copier

class PaletteExpectationsTest(unittest.TestCase):
    def fixture(self):
        rom=bytearray(0x100000)
        for bank in builder.BANKS:
            offset=builder.offset(bank);rom[offset:offset+len(builder.payload())]=builder.payload()
        return rom

    def test_only_enemy_bullet_role_changes(self):
        with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent') as parent:
            result=obj.expected_obj_table(self.fixture())
            parent.assert_called_once()
        self.assertEqual([(i,a,b) for i,(a,b) in enumerate(zip(obj.build_obj_pal_table(),result)) if a!=b],[(15,0,3)])

    def test_each_live_initializer_required(self):
        for bank in builder.BANKS:
            rom=self.fixture();rom[builder.offset(bank)]^=1
            with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent'):
                with self.assertRaisesRegex(ValueError,'initializer'):obj.expected_obj_table(rom)

    def test_unknown_build_does_not_get_new_role(self):
        self.assertEqual(obj.expected_obj_table(self.fixture()),obj.build_obj_pal_table())

    def test_parent_authentication_failure_propagates(self):
        with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent',side_effect=ValueError('bad delta')):
            with self.assertRaisesRegex(ValueError,'bad delta'):obj.expected_obj_table(self.fixture())

    def test_bg_component_requires_unchanged_full_table(self):
        with patch.object(bg_lineage,'is_candidate',side_effect=[True,False]),patch.object(bg_lineage,'authenticated_parent',return_value=b'parent') as parent:
            result=bg.expected_stage1_table(b'child')
            parent.assert_called_once_with(b'child',(bg.DUNGEON_TABLE_OFFSET,bg.DUNGEON_TABLE_OFFSET+256))
            self.assertEqual(result,bg.EXPECTED_TABLE)

    def test_menu_inheritance_authenticates_both_tables_and_entry(self):
        parent_rom=bytes(0x80000)
        with patch.object(bg_lineage,'is_candidate',side_effect=[True,False]),patch.object(bg_lineage,'authenticated_parent',return_value=parent_rom) as parent:
            result=menu.menu_oracle(b'child')
            parent.assert_called_once_with(b'child',
                (menu.BANK13_LUT,menu.BANK13_LUT+256),
                (menu.BANK20_LUT,menu.BANK20_LUT+256),
                (menu.MENU_FIRST_ENTRY,menu.MENU_FIRST_ENTRY+len(menu.MENU_WRAPPER_PREFIX)))
        self.assertEqual(result,menu.menu_oracle(parent_rom))

    def test_menu_parent_authentication_failure_is_not_swallowed(self):
        with patch.object(bg_lineage,'is_candidate',return_value=True),patch.object(bg_lineage,'authenticated_parent',side_effect=ValueError('changed menu')):
            with self.assertRaisesRegex(ValueError,'changed menu'):menu.menu_oracle(b'child')

    def test_protocol_requires_every_unchanged_component(self):
        rom=bytearray(b'\xff'*0x80000)
        ranges=[]
        for bank,address,code in protocol.expected_parts():
            offset=bank*0x4000+address-(0x4000 if bank else 0)
            rom[offset:offset+len(code)]=code
            ranges.append((offset,offset+len(code)))
        with patch.object(bg_lineage,'is_candidate',return_value=True),patch.object(bg_lineage,'authenticated_parent',return_value=bytes(rom)) as parent:
            self.assertEqual(protocol.authenticate(b'child')['name'],protocol.NAME)
            parent.assert_called_once_with(b'child',*ranges)
        rom[ranges[-1][0]]^=1
        with patch.object(bg_lineage,'is_candidate',return_value=True),patch.object(bg_lineage,'authenticated_parent',return_value=bytes(rom)):
            with self.assertRaisesRegex(ValueError,'unknown completed-map'):protocol.authenticate(b'child')

    def test_pickup_art_authenticates_entire_source_table(self):
        with patch.object(bg_lineage,'is_candidate',side_effect=[True,False]),patch.object(bg_lineage,'authenticated_parent',return_value=b'parent') as parent:
            self.assertEqual(art.expected_stage1_table(b'child'),art.EXPECTED_TABLE)
            parent.assert_called_once_with(b'child',(art.BG_TABLE_OFFSET,art.BG_TABLE_OFFSET+256))

    def test_pickup_helpers_keep_exact_scene_read_exception(self):
        start=0xDABB-pickups.RUNTIME_HELPER_ADDR
        helpers=[bytearray(pickups.RUNTIME_HELPER_SIZE) for _ in range(2)]
        helpers[0][start:start+3]=bytes.fromhex('CDDFDB')
        helpers[1][start:start+3]=bytes.fromhex('FA80D8')
        import release_lock_lineage
        with patch.object(bg_lineage,'is_candidate',return_value=True),patch.object(bg_lineage,'authenticated_parent',return_value=b'parent') as parent,patch.object(release_lock_lineage,'is_candidate',return_value=True):
            self.assertTrue(pickups.release_lock_scene_read(b'child',helpers))
            ranges=parent.call_args.args[1:]
            self.assertEqual(len(ranges),4)
            self.assertEqual(sum(end-start for start,end in ranges),2*pickups.RUNTIME_HELPER_SIZE)
            helpers[0][0]^=1
            self.assertFalse(pickups.release_lock_scene_read(b'child',helpers))

    def test_semantic_expansion_requires_both_complete_banks_and_table(self):
        with patch.object(bg_lineage,'is_candidate',return_value=True),patch.object(bg_lineage,'authenticated_parent',side_effect=ValueError('changed span')) as parent:
            with self.assertRaisesRegex(ValueError,'changed span'):
                hazards.semantic_expansion_is_exact(b'child')
            parent.assert_called_once_with(b'child',(19*0x4000,21*0x4000),(hazards.BG_TABLE_OFFSET,hazards.BG_TABLE_OFFSET+256))

    def test_copier_authentication_and_failure_propagate(self):
        with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent',return_value=b'parent') as parent:
            self.assertEqual(copier.copier_contract_rom(b'child'),b'parent')
            parent.assert_called_once_with(b'child',(copier.COPIER_START,copier.COPIER_END))
        with patch.object(lineage,'is_candidate',return_value=True),patch.object(lineage,'authenticated_parent',side_effect=ValueError('changed copier')):
            with self.assertRaisesRegex(ValueError,'changed copier'):
                copier.reviewed_postcomputed_copier(b'child')

if __name__=='__main__':unittest.main()
