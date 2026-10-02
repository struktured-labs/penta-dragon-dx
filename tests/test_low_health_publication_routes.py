import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from verify_low_health_flicker import publication_route_profile, publication_routes_exact


class PublicationRoutes(unittest.TestCase):
    def test_exact_rom_and_counter_negative_controls(self):
        root=Path(__file__).resolve().parents[1]
        rom=(root/'tmp/room03-animation-envelope-r440/candidate.gb').read_bytes()
        profile=publication_route_profile(rom)
        self.assertEqual(profile,'r440-bounded-room03')
        modified=bytearray(rom);modified[19*0x4000+0x2B81]^=1
        self.assertEqual(publication_route_profile(bytes(modified)),'')
        counts=dict(dispatch=223,front=64,route_completed=223,route_bypass=159,
            route_invalid=0,route_pending=0,pure_helper=224)
        self.assertTrue(publication_routes_exact(counts,profile))
        self.assertFalse(publication_routes_exact(counts,''))
        self.assertFalse(publication_routes_exact(counts,'unknown'))
        for key,value in counts.items():
            if key=='pure_helper':continue # raw breakpoint callbacks are diagnostic
            self.assertFalse(publication_routes_exact(dict(counts,**{key:value+1}),profile),key)
        for key in ('route_completed','route_bypass','route_invalid','route_pending'):
            missing=dict(counts);del missing[key]
            self.assertFalse(publication_routes_exact(missing,profile),key)
