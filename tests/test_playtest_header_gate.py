import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import verify_live_regression as live
import verify_playtest_header_regression as gate
import verify_clean_stage_headers as check


class HeaderGateTest(unittest.TestCase):
    def test_pre_stream_profile_cannot_omit_the_header_regression(self):
        name = 'playtest_header_data_and_timing'
        with patch.object(live, 'registered_gate_names', return_value={name}):
            selected, errors = live.profile_gates(Path('unit-only'))
        self.assertEqual(errors, [])
        self.assertEqual(selected, (name,))
        with patch.object(live, 'registered_gate_names', return_value={name}), patch.object(
            live, 'LIVE_GATES', tuple(n for n in live.LIVE_GATES if n != name)
        ):
            _, errors = live.profile_gates(Path('unit-only'))
        self.assertTrue(any('omitted' in error for error in errors))

    def test_common_timing_regression_fails_even_with_clean_headers(self):
        control=dict.fromkeys(('af_after','bc_after','de_after','hl_after',
                              'sp_after','bank','dc09_after'),'1')
        control['cycles']='3304';candidate={**control,'cycles':'3336'}
        for target in range(7):
            self.assertTrue(check.contract_differences(candidate,control,target,True))
        for target in (7,8):
            self.assertEqual(check.contract_differences(candidate,control,target,True),[])
        self.assertEqual(check.contract_differences(control,control,0,True),[])
        candidate['sp_after']='0'
        self.assertTrue(check.contract_differences(candidate,control,8,True))

    def test_corruption_is_limited_to_two_records_and_checksum(self):
        rom=bytearray(0x100000)
        for address in (0x7C91,0x7CAE):rom[address:address+9]=bytes(range(1,10))
        with patch.object(gate.lineage,'is_candidate',return_value=True):
            result=gate.corrupt_control(bytes(rom))
        expected={0x14E,0x14F}
        for address in (0x7C91,0x7CAE):
            offset=gate.layout.offset(gate.layout.CLEAN_TABLE)+address-0x7BB3
            expected.update(range(offset,offset+9))
            self.assertEqual(result[offset:offset+9],rom[address:address+9])
        self.assertTrue({i for i,(a,b) in enumerate(zip(rom,result)) if a!=b}<=expected)

    def test_unknown_candidate_cannot_seed_control(self):
        with self.assertRaisesRegex(ValueError,'exact'):gate.corrupt_control(bytes(0x100000))


if __name__=='__main__':unittest.main()
