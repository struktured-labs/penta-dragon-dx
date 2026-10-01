"""#45 experimental fade structure; not timing or release acceptance."""
import hashlib
import csv
import json
import mmap
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_return_cgb_fade_trial import build, payload, BASE


class ReturnCgbFadeTrial(unittest.TestCase):
    def test_card_tail_fixed_fallback_keeps_initial_map_white(self):
        findings=[]
        for name,start in (('return-initial-map-exit-01',4801),('return-cgb-fade-exit-10',4802)):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists():self.skipTest('paired route evidence unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            path=Path(receipt['native_capture_directory'])/'native.states'
            with path.open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),receipt['native_capture']['hashes']['native.states'])
                with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as states:
                    def state(n):return states[(n-1)*71680:n*71680]
                    white=bytes.fromhex('ff7f')*32
                    self.assertEqual(state(start)[0x5c80],2)
                    whites=[state(n)[0xd4:0x114]==white for n in range(start,start+18)]
                    resume=next(n for n in range(start+4,start+100) if state(n)[0x3c1]==1)
                    findings.append((all(whites),resume))
        self.assertEqual(findings,[(False,4858),(True,4859)])
        # Known-broken parent fails the visual invariant; one-frame timing
        # difference remains visible and prevents broad acceptance.

    def test_initial_card_caller_keeps_native_fade_and_cold_telemetry(self):
        parent=ROOT/'tmp/return-initial-map-trial-01/candidate.gb'
        base=ROOT/'tmp/return-cgb-fade-own-entry-10'
        if not parent.exists() or not (base/'receipt.json').exists():self.skipTest('cold fallback evidence unavailable')
        rom=build(parent.read_bytes(),True,True,True,True,True,True)
        sha='f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29'
        self.assertEqual(hashlib.sha256(rom).hexdigest(),sha)
        self.assertEqual(rom[0x4143:0x4146],bytes.fromhex('CD C7 75'))
        self.assertEqual(rom[0x75f0:0x75f3],bytes.fromhex('C3 89 42'))
        self.assertEqual(rom[0xf33:0xf66],parent.read_bytes()[0xf33:0xf66])
        receipt=json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['status'],0)
        self.assertEqual(receipt['rom_sha256'],sha)
        rows=[]
        for name in ('return-initial-map-own-entry-01','return-cgb-fade-own-entry-10'):
            with (ROOT/'tmp'/name/'trace.tsv').open() as f:rows.append(list(csv.DictReader(f,delimiter='\t')))
        self.assertEqual(len(rows[0]),3600)
        self.assertEqual(*rows)
        # Native PCM and instruction timing equivalence are separate requirements.

    def test_card_tail_trial_hides_map_but_retains_cold_regression(self):
        path=ROOT/'tmp/return-cgb-fade-exit-09/receipt.json'
        if not path.exists():self.skipTest('card-tail replay unavailable')
        r=json.loads(path.read_text())
        self.assertEqual(r['status'],0)
        self.assertEqual(r['rom_sha256'],'73a68c346f5890db77eb62a6b3ec498e79082c9df0847d632893016cac6b1c66')
        with (Path(r['native_capture_directory'])/'native.states').open('rb') as f:
            self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),r['native_capture']['hashes']['native.states'])
            with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as states:
                for n in range(4934,4951):
                    state=states[(n-1)*71680:n*71680]
                    self.assertEqual(state[0x5c80],2)
                    self.assertEqual(state[0xd4:0x114],bytes.fromhex('ff7f')*32)
        rows=[]
        for name in ('return-initial-map-own-entry-01','return-cgb-fade-own-entry-09'):
            with (ROOT/'tmp'/name/'trace.tsv').open() as f:rows.append(list(csv.DictReader(f,delimiter='\t')))
        diffs=[i+1 for i,(a,b) in enumerate(zip(*rows)) if a!=b]
        self.assertEqual((len(diffs),diffs[0]),(2353,583))
        # Visual improvement cannot qualify a build that changes the cold route.

    def test_card_fade_stack_identifies_scoped_tail_entry(self):
        """#45: the earlier flash belongs to the card tail, not15D7 setup."""
        base=ROOT/'tmp/return-initial-map-exit-01'
        if not (base/'receipt.json').exists():self.skipTest('parent return unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        rom=(base/'candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb')
        self.assertEqual(rom[0x159f:0x15a2],bytes.fromhex('CD C7 75'))
        self.assertEqual(rom[0x75e8:0x75f3],bytes.fromhex('CD 47 0F 06 64 CD 68 40 C3 33 0F'))
        self.assertEqual(rom[0xfcc:0xfd0],bytes.fromhex('E4 90 40 00'))
        path=Path(receipt['native_capture_directory'])/'native.states'
        if not path.exists():self.skipTest('parent native states unavailable')
        with path.open('rb') as stream:
            self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),
                             receipt['native_capture']['hashes']['native.states'])
            with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as states:
                for n,bgp in ((4768,0xe4),(4773,0x90),(4777,0x40)):
                    state=states[(n-1)*71680:n*71680]
                    self.assertEqual(state[0x5c80],0x18)
                    self.assertEqual(state[0x3ba],0)
                    self.assertEqual(state[0x347],bgp)
                    sp=int.from_bytes(state[40:42],'little')
                    self.assertEqual(sp,0xdfe1)
                    off=0x4400+sp-0xc000
                    # Saved AF, wait return0F5D, saved BC/HL, caller15A2.
                    self.assertEqual(state[off+2:off+4],bytes.fromhex('5D 0F'))
                    self.assertEqual(state[off+8:off+10],bytes.fromhex('A2 15'))

    def test_fused_setup_restores_palette_with_neutral_observer(self):
        receipts=[]
        for name in ('return-cgb-fade-window-07','return-cgb-fade-window-control-07'):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists():self.skipTest('fused replay unavailable')
            r=json.loads((base/'receipt.json').read_text())
            self.assertEqual(r['status'],0)
            self.assertFalse(r['observer_memory_writes'])
            self.assertEqual(r['rom_sha256'],'4c30a79db223c687a6f027747248946352328b58ea173dcc3574193061624c1f')
            self.assertEqual(r['source_state_sha256'],'7e5b6008093eb7afa25f631c5dc8082141d2a8d28318ef02a35f898073247e58')
            for ext in ('video','states','s16le','timeline.tsv'):
                with (Path(r['native_capture_directory'])/f'native.{ext}').open('rb') as f:
                    self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),r['native_capture']['hashes'][f'native.{ext}'])
            receipts.append(r)
        for ext in ('video','states','s16le','timeline.tsv'):
            self.assertEqual(*(r['native_capture']['hashes'][f'native.{ext}'] for r in receipts))
        with (ROOT/'tmp/return-cgb-fade-window-07/cram-timing.tsv').open() as f:
            writes=[r for r in csv.DictReader(f,delimiter='\t') if r['bank']=='14' and 0x551c<=int(r['pc'],16)<0x5b70]
        self.assertEqual(len(writes),320)
        self.assertEqual({r['mode'] for r in writes},{'1'})
        # Final initial-whitening writes reach the LY0/mode1 tail of VBlank;
        # do not mistake this observed run for a broad timing-margin guarantee.
        self.assertEqual((writes[0]['ly'],writes[63]['ly']),('150','0'))
        states=(Path(receipts[0]['native_capture_directory'])/'native.states').read_bytes()
        backup=states[-71680+0xc300:-71680+0xc340]
        self.assertEqual(backup,states[0xd4:0x114])
        self.assertEqual(backup,bytes(int(r['value'],16) for r in writes[-64:]))
        with self.assertRaises(ValueError):payload(fused_setup=True)

    def test_scheduled_return_reduces_but_does_not_eliminate_delay(self):
        base=ROOT/'tmp/return-cgb-fade-exit-06'
        if not (base/'receipt.json').exists():self.skipTest('scheduled return evidence unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['status'],0)
        self.assertEqual(receipt['rom_sha256'],'e3d342b56000badcd28aa8a8aedb41a2c2c6dc4189ee30548f10cf7832e1b773')
        self.assertEqual(receipt['source_state_sha256'],'1eb99fe322850dfeda5380af187074f31bc72842272c2efab235ed117ec62103')
        path=Path(receipt['native_capture_directory'])/'native.states'
        if not path.exists():self.skipTest('native scheduled return unavailable')
        with path.open('rb') as stream:
            self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),receipt['native_capture']['hashes']['native.states'])
            with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as states:
                self.assertEqual(len(states),6000*71680)
                def frame(n):return states[(n-1)*71680:n*71680]
                self.assertEqual(frame(4803)[0x3c1],0)
                resume=next(n for n in range(4804,4900) if frame(n)[0x3c1]==1)
                self.assertEqual(resume,4860)  # Parent4858; old trial4864.
                white=bytes.fromhex('ff7f')*32
                self.assertNotEqual(frame(4805)[0xd4:0x114],white)
                self.assertEqual(frame(4807)[0xd4:0x114],white)
                changes=[];previous=0
                for n in range(4801,4861):
                    bgp=frame(n)[0x347]
                    if bgp!=previous:changes.append((n,bgp));previous=bgp
                self.assertEqual(changes,[(4822,0x40),(4831,0x90),(4839,0xe4)])
        # A measured improvement is not permission to lose the remaining failure.

    def test_scheduled_variant_only_moves_four_wait_counts(self):
        path=ROOT/'tmp/return-initial-map-trial-01/candidate.gb'
        if not path.exists():self.skipTest('pinned parent unavailable')
        parent=path.read_bytes()
        old=build(parent,True,True,True)
        new=build(parent,True,True,True,True)
        self.assertEqual(hashlib.sha256(new).hexdigest(),
                         'e3d342b56000badcd28aa8a8aedb41a2c2c6dc4189ee30548f10cf7832e1b773')
        diffs=[i for i,(a,b) in enumerate(zip(old,new)) if a!=b and i not in (0x14e,0x14f)]
        self.assertEqual(len(diffs),4)
        for i in diffs:
            self.assertEqual(old[i-1:i+1],bytes((6,8)))
            self.assertEqual(new[i-1:i+1],bytes((6,7)))
        with self.assertRaises(ValueError):build(parent,scheduled_write=True)
        # Structural isolation only: actual cadence and earlier flash still need replay.

    def test_return_window_waits_and_late_vblank_counterexample(self):
        captures=[]
        for name in ('return-cgb-fade-window-05','return-cgb-fade-window-control-05'):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('window evidence unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['rom_sha256'],'e7811f61995b30dc6070bc5ab886f01dcb06179c22bde0d5ad7af820ff7f6035')
            self.assertEqual(receipt['source_state_sha256'],'7d21d276f5584c2adeeb6bfeed1e17e4f474dc86037f1d6e2db4fb9af21ce59f')
            hashes={}
            for ext in ('video','states','s16le','timeline.tsv'):
                path=Path(receipt['native_capture_directory'])/f'native.{ext}'
                if not path.exists():self.skipTest('native window files unavailable')
                with path.open('rb') as stream: hashes[ext]=hashlib.file_digest(stream,'sha256').hexdigest()
                self.assertEqual(hashes[ext],receipt['native_capture']['hashes'][f'native.{ext}'])
            captures.append(hashes)
        self.assertEqual(*captures)
        with (ROOT/'tmp/return-cgb-fade-window-05/menu-critical.tsv').open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        first=None; waits=[]
        for row in rows:
            # The entry is also the polling loop: retain only the first visit
            # after each completed acquisition, not every polling iteration.
            if row['event']=='pair_before' and first is None:first=row
            if row['event']=='pair_after':
                self.assertIsNotNone(first)
                self.assertEqual(int(row['ly'],16),144)
                waits.append((int(first['ly'],16),int(first['stat'],16)&3,
                              int(row['cycle'])-int(first['cycle'])))
                first=None
        self.assertEqual(waits,[(113,0,27464),(5,3,126600),(149,1,135408),
                                (149,1,135456),(152,1,132488),(149,1,135448)])
        self.assertIsNone(first)
        # Being in mode1 alone is not enough: LY152 is a retained unsafe
        # late-window counterexample for a full-deck immediate writer.

    def test_combined_entry_actual_return_retains_flash_and_latency_failure(self):
        """Cold timing success must not qualify the failing secret return (#45)."""
        results=[]
        for name,sha in (
            ('return-initial-map-exit-01','916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb'),
            ('return-cgb-fade-exit-05','e7811f61995b30dc6070bc5ab886f01dcb06179c22bde0d5ad7af820ff7f6035'),
        ):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('local return evidence unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertEqual(receipt['rom_sha256'],sha)
            self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),sha)
            path=Path(receipt['native_capture_directory'])/'native.states'
            if not path.exists(): self.skipTest('native return evidence unavailable')
            with path.open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),
                                 receipt['native_capture']['hashes']['native.states'])
                with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as states:
                    self.assertEqual(len(states),6000*71680)
                    def frame(n): return states[(n-1)*71680:n*71680]
                    self.assertEqual(frame(4801)[0x5c80],2)
                    self.assertEqual(frame(4803)[0x3c1],0)
                    resume=next(n for n in range(4804,4900) if frame(n)[0x3c1]==1)
                    white=bytes.fromhex('ff7f')*32
                    whites=[n for n in range(4801,4850) if frame(n)[0xd4:0x114]==white]
                    # BGP00 alone does not make CGB colors white: early flash survives.
                    self.assertEqual(frame(4805)[0x347],0)
                    self.assertNotEqual(frame(4805)[0xd4:0x114],white)
                    results.append((resume,whites))
        self.assertEqual(results,[(4858,[]),(4864,list(range(4807,4826)))])
        # This passing evidence test records a FAILED ROM trial, not acceptance.

    def test_combined_entry_preserves_setup_and_recovers_cold_exit_phase(self):
        path=ROOT/'tmp/return-initial-map-trial-01/candidate.gb'
        if not path.exists():self.skipTest('pinned local parent unavailable')
        parent=path.read_bytes()
        rom=build(parent,return_scoped=True,isolated=True,combined_entry=True)
        self.assertEqual(rom[0x15d7:0x15da],parent[0x15d7:0x15da])
        self.assertEqual(rom[0xf7a:0xf9d],parent[0xf7a:0xf9d])
        self.assertEqual(hashlib.sha256(rom).hexdigest(),'e7811f61995b30dc6070bc5ab886f01dcb06179c22bde0d5ad7af820ff7f6035')
        with self.assertRaises(ValueError):build(parent,combined_entry=True)
        rows=[]
        anchors=[]
        for name in ('return-cgb-fade-entry-parent-trace-01','return-cgb-fade-entry-trace-05'):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists():self.skipTest('combined-entry replay unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            with (base/'trace.tsv').open() as stream:rows.append(list(csv.DictReader(stream,delimiter='\t')))
            with (base/'return-build.tsv').open() as stream:
                anchors.append([(r['pc'],int(r['cycle'])) for r in csv.DictReader(stream,delimiter='\t')
                                if r['pc'] in ('0F7A','15E2') and int(r['frame'])>2500])
        self.assertEqual(len(rows[0]),2700)
        self.assertEqual(*rows)
        # Entry overhead remains; equality at the exit is not instruction/PCM parity.
        self.assertEqual(anchors,[ [('0F7A',367298032),('15E2',372548560)],
                                  [('0F7A',367299152),('15E2',372548560)] ])

    def test_isolated_variant_leaves_shared_fade_and_menu_entry_unchanged(self):
        path=ROOT/'tmp/return-initial-map-trial-01/candidate.gb'
        if not path.exists(): self.skipTest('pinned local parent unavailable')
        parent=path.read_bytes();rom=build(parent,return_scoped=True,isolated=True)
        self.assertEqual(rom[0xf7a:0xf9d],parent[0xf7a:0xf9d])
        self.assertEqual(rom[20*0x4000+0x28f:20*0x4000+0x292],
                         parent[20*0x4000+0x28f:20*0x4000+0x292])
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         'd9dc5d0700f9bd553aaf05ad35a0f221c64841db590157910f334b2964d06e85')

    def test_cold_timing_counterexample_is_retained(self):
        names=('return-initial-map-own-entry-01','return-cgb-fade-own-entry-04')
        paths=[ROOT/'tmp'/name/'trace.tsv' for name in names]
        if not all(p.exists() for p in paths): self.skipTest('cold-route evidence unavailable')
        rows=[]
        for path in paths:
            with path.open() as stream:
                rows.append(list(csv.DictReader(stream,delimiter='\t')))
        self.assertEqual([len(r) for r in rows],[3600,3600])
        differing=[i+1 for i,(a,b) in enumerate(zip(*rows)) if a!=b]
        self.assertTrue(differing)
        self.assertEqual(differing[0],2651)
        # Structural hook isolation is not sufficient evidence of timing parity.

    def test_first_entry_shift_is_between_setup_and_unchanged_native_fade(self):
        names=('return-cgb-fade-entry-parent-trace-01','return-cgb-fade-entry-trace-04')
        traces=[]
        for name in names:
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('entry trace unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertEqual(receipt['state_change'],'cold boot, no save present')
            self.assertEqual(hashlib.sha256((base/'candidate.gb').read_bytes()).hexdigest(),receipt['rom_sha256'])
            with (base/'return-build.tsv').open() as stream:
                rows=list(csv.DictReader(stream,delimiter='\t'))
            traces.append({pc:next(r for r in rows if r['pc']==pc and 2600<=int(r['frame'])<=2660)
                           for pc in ('16DD','0F7A','15E2')})
        parent,trial=traces
        self.assertEqual(parent['16DD']['cycle'],trial['16DD']['cycle'])
        self.assertEqual(int(trial['0F7A']['cycle'])-int(parent['0F7A']['cycle']),2104)
        self.assertEqual(int(trial['15E2']['frame'])-int(parent['15E2']['frame']),2)
        self.assertEqual(parent['0F7A']['source'],trial['0F7A']['source'])

    def test_observed_writes_restore_live_backup_in_vblank_without_observer_drift(self):
        bases=[ROOT/'tmp'/n for n in ('return-cgb-fade-window-02','return-cgb-fade-window-control-02')]
        if not all((b/'receipt.json').exists() for b in bases):
            self.skipTest('local fade replay unavailable')
        captures=[]
        for base in bases:
            r=json.loads((base/'receipt.json').read_text())
            self.assertEqual(r['status'],0)
            self.assertFalse(r['observer_memory_writes'])
            self.assertEqual(r['rom_sha256'],'8187e912d82694a29b9b4b921b3e0f2960b4472616baebb3fe0a96af650d3889')
            self.assertEqual(r['source_state_sha256'],'2316ecd6319c4a0e590b02711afe5e25f991d51094cfd5caa3f5ce964c46e77f')
            captures.append((r,Path(r['native_capture_directory'])))
        for ext in ('s16le','video','states','timeline.tsv'):
            hashes=[]
            for receipt,path in captures:
                digest=hashlib.sha256((path/f'native.{ext}').read_bytes()).hexdigest()
                self.assertEqual(digest,receipt['native_capture']['hashes'][f'native.{ext}'])
                hashes.append(digest)
            self.assertEqual(*hashes)
        with (bases[0]/'cram-timing.tsv').open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        owned=[r for r in rows if r['bank']=='14' and BASE<=int(r['pc'],16)<BASE+len(payload())]
        self.assertEqual(len(owned),320)
        self.assertTrue(all(r['mode']=='1' for r in owned))
        states=(captures[0][1]/'native.states').read_bytes()
        last=states[-71680:]
        restored=bytes(int(r['value'],16) for r in owned[-64:])
        self.assertEqual(restored,last[0xc300:0xc340])

    def test_exact_patch_and_native_wait_loop_preserved(self):
        path=ROOT/'tmp/return-initial-map-trial-01/candidate.gb'
        if not path.exists(): self.skipTest('pinned local parent unavailable')
        parent=path.read_bytes();rom=build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '8187e912d82694a29b9b4b921b3e0f2960b4472616baebb3fe0a96af650d3889')
        self.assertEqual(rom[0xf88:0xf8f],parent[0xf88:0xf8f])
        self.assertEqual(rom[0xf92:0xf9d],parent[0xf92:0xf9d])
        offset=20*0x4000+BASE-0x4000
        allowed=set(range(offset,offset+len(payload())))|{0x14e,0x14f}
        for addr in (0x15d7,0xf8f,20*0x4000+0x28f): allowed.update(range(addr,addr+3))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,rom)) if a!=b))
        with self.assertRaises(ValueError): build(rom)

    def test_callsite_guard_and_original_menu_dispatch_remain(self):
        code=payload()
        self.assertIn(bytes.fromhex('F8 0D 7E FE 15'),code)
        self.assertIn(bytes.fromhex('2B 7E FE DD'),code)
        self.assertIn(bytes.fromhex('E1 C3 00 47'),code)
        self.assertIn(bytes.fromhex('E1 F1 2A E0 47 C3 9A 09'),code)
