#!/usr/bin/env python3
"""Build the #23/#18/#31/#28 candidate from original cartridge and palette source.

Historical overlay contracts require their exact neutral Game Over parent.
Compile that parent using an explicitly recorded derived palette, authenticate
each historical stage, then apply the independently bounded new fixes. No
retained candidate ROM is used as an input. This is construction, not readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import build_restart_candidate as restart
import build_sara_atomic_pose as sara
import build_secret_chr_restore as graphics
import build_secret_palette_sources as secret_palette
import build_gameover_color as gameover
import build_native_projectile_templates as projectiles
import build_continue_input as continuation


def digest(data):
    return hashlib.sha256(data).hexdigest()


# Release lock 2026-10-01: defer #14 (doorway helper timing) and #34 (select
# buffer). #14 is since fixed by the cycle-identical sara-overhang-priority
# stage at the end of the return-fade chain. Every remaining stage is re-pinned with byte-identical change sets;
# evidence in docs/audit/release-lock-20261001-repin.md.
PINS = {
    False: dict(presentation='d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5',
                arena='585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db',
                completion='d901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a',
                secret_alias='665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7',
                chunks='2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306',
                initial='916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb',
                fade='f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29',
                deadline='8ac7fbe3b290f4743280961541fb81746046e89bbdabde6f2b914e73fd60888c',
                compact='126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b'),
    True: dict(presentation='9ca97f860289a3d1a0e420ff4a7243ddb56550a23d8608d0f055781e24c8a05b',
               arena='1b3bbf845a096dd5e5818b4f98fe68cb00f95468ad1a7ad8926c4946d3f2ed4e',
               completion='d90f5fc7245091d6f42404f04eab02672474a4cf559897a0bcfb397f592c81f0',
               secret_alias='e48091478df6248fca9b45fa25aa8d9402daf18981bb26840a6ffaf1a3d62eed',
               chunks='f23d6d091211a754aff9eaab0694b59e258a89de5e2e1569c53d6d50008214bc',
               initial='4d8f3fad9cb57f24cdd442402a5b4d2a67f9aeea683e20328d4ed8fd02645f8e',
               fade='2992a8a2dbef89d5070afd97c498c1db0ab1d8f6cc46f65cd0ecd4f6937415ed',
               deadline='3540f75e14b7634d0dda6afb5199e4abc6c9a47c03fbb09eb2b610dd23ac7241',
               compact='6ec44fe6b77dd59088c06a07e0631187737e8471365a68806c0d5aa407563b97',
               # Footer glyph GDMA only in a VRAM-accessible window (returned
               # title read "DX V3901" once #34 no longer masked the timing).
               title_glyph='792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db',
               # Continue into a miniboss reloads BG palettes (sequencer reload for scene
               # $0A) and the CRAM source writer can no longer straddle mode 3.
               continue_miniboss='db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8',
               # #14: Sara regains OBJ-to-BG priority under black ceiling overhangs
               # (fused flash/priority helper, cycle-identical quadrant flags).
               overhang_priority='ffc29f4e29f2c2f9995f132c08676624ad92a206b822b3afdf835be3ad072feb'),
}


def presentation_chain(source, reported, release_lock=False):
    """Rebuild the exact tested experimental chain; never promote implicitly."""
    import compose_stream_presentation_trial as composition
    import build_palette_window_trial as window
    import build_select_buffer_trial as select
    import build_handheld_palette_trial as handheld
    import build_title_local_guard_trial as title
    import build_ted_menu_reinstall_trial as ted
    import build_five_point_star_trial as star
    current, branches = composition.build(source, reported, defer_ceiling=release_lock)
    records = [dict(name='presentation-composition', parent_sha256=digest(source),
                    reported_sha256=digest(reported), candidate_sha256=digest(current),
                    branches=branches)]
    if release_lock:
        records[0]['deferred_issues'] = [14]
    for name, module in (('palette-window',window), ('select-buffer',select),
                         ('handheld-palette',handheld), ('title-local-guard',title),
                         ('ted-menu-reinstall',ted), ('five-point-star',star)):
        if release_lock and name == 'select-buffer':
            continue
        result = module.build(current)
        records.append(dict(name=name, parent_sha256=digest(current),
                            candidate_sha256=digest(result)))
        current = result
    if digest(current) != PINS[release_lock]['presentation']:
        raise ValueError('presentation chain differs from tested experimental pin')
    return current, records


def arena_alias_chain(parent, completion_safe=False, release_lock=False):
    """Reproduce #27 experiments explicitly; defaults remain unchanged."""
    import build_arena_sound_alias_trial as alias
    import build_arena_graphics_owner_trial as owner
    import build_arena_alias_fastpath_trial as fastpath
    records = []
    for name, module in (('arena-sound-alias',alias),
                         ('arena-graphics-owner',owner),
                         ('arena-alias-fastpath',fastpath)):
        result = module.build(parent)
        records.append(dict(name=name,parent_sha256=digest(parent),
                            candidate_sha256=digest(result),
                            builder=str(Path(module.__file__).resolve()),
                            builder_sha256=digest(Path(module.__file__).read_bytes())))
        parent = result
    if digest(parent) != PINS[release_lock]['arena']:
        raise ValueError('arena alias chain differs from tested experimental pin')
    if completion_safe:
        import build_arena_completion_safe_trial as completion
        result = completion.build(parent)
        records.append(dict(name='arena-completion-safe', parent_sha256=digest(parent),
                            candidate_sha256=digest(result),
                            builder=str(Path(completion.__file__).resolve()),
                            builder_sha256=digest(Path(completion.__file__).read_bytes())))
        parent = result
        if digest(parent) != PINS[release_lock]['completion']:
            raise ValueError('completion-safe chain differs from tested experimental pin')
    return parent, records


def return_fade_chain(parent, release_lock=False):
    """#45 reproduce trial16 from the source-built secret-alias parent."""
    import build_secret_alias_chunk_trial as chunks
    import build_return_initial_map_trial as initial
    import build_return_cgb_fade_trial as fade
    import build_return_card_deadline_trial as deadline
    import build_return_card_compact_trial as compact
    records=[]
    pins=PINS[release_lock]
    stages=(
        ('secret-alias-chunks',chunks,chunks.build,pins['chunks']),
        ('return-initial-map',initial,initial.build,pins['initial']),
        ('return-cgb-fade',fade,lambda data: fade.build(data,return_scoped=True,
            isolated=True,combined_entry=True,scheduled_write=True,
            fused_setup=True,card_tail=True),pins['fade']),
        ('return-card-deadline',deadline,deadline.build,pins['deadline']),
        ('return-card-compact',compact,compact.build,pins['compact']))
    if release_lock:
        import build_title_glyph_window_trial as glyph
        import build_continue_miniboss_reload_trial as continue_reload
        import build_sara_overhang_priority as overhang
        stages+=(('title-glyph-window',glyph,glyph.build,pins['title_glyph']),
                 ('continue-miniboss-reload',continue_reload,continue_reload.build,
                  pins['continue_miniboss']),
                 ('sara-overhang-priority',overhang,overhang.build,
                  pins['overhang_priority']))
    for name,module,transform,expected in stages:
        result=transform(parent)
        if digest(result)!=expected:
            raise ValueError(f'{name} differs from tested experimental pin')
        records.append(dict(name=name,parent_sha256=digest(parent),
                            candidate_sha256=digest(result),
                            builder=str(Path(module.__file__).resolve()),
                            builder_sha256=digest(Path(module.__file__).read_bytes())))
        parent=result
    return parent,records


def late_return_fade_chain(parent):
    """#45 exact46eb trial, including its unresolved fixed-ROM allocation."""
    import build_initial_map_fastpath_trial as initial
    import build_fixed_fade_route_trial as route
    import build_final_fade_late_window_trial as window
    records = []
    for name, module, transform, expected in (
        ('initial-map-native-fastpath', initial, initial.build, route.PARENT),
        ('fixed-fade-stage-routing', route, route.build, window.PARENT),
        ('final-fade-late-window', window, lambda data: window.build(data)[0],
         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'),
    ):
        result = transform(parent)
        if digest(result) != expected:
            raise ValueError(f'{name} differs from tested experimental pin')
        records.append(dict(name=name, parent_sha256=digest(parent),
                            candidate_sha256=digest(result),
                            builder=str(Path(module.__file__).resolve()),
                            builder_sha256=digest(Path(module.__file__).read_bytes())))
        parent = result
    return parent, records


def build(output, presentation=False, arena_alias=False, arena_completion_safe=False,
          secret_sound_alias=False, return_fade=False, experimental_late_return_fade=False,
          release_lock=False):
    if release_lock and not return_fade:
        raise ValueError('release lock re-pins the full return-fade chain only')
    if release_lock and experimental_late_return_fade:
        raise ValueError('release lock does not re-pin the late return fade chain')
    if experimental_late_return_fade and not return_fade:
        raise ValueError('late return fade requires explicit return fade chain')
    if return_fade and not secret_sound_alias:
        raise ValueError('return fade requires explicit secret sound alias chain')
    if secret_sound_alias and not arena_completion_safe:
        raise ValueError('secret sound alias requires explicit completion-safe chain')
    if arena_completion_safe and not arena_alias:
        raise ValueError('completion-safe chain requires explicit arena alias chain')
    if arena_alias and not presentation:
        raise ValueError('arena alias chain requires explicit presentation chain')
    output = output.resolve()
    if output.exists() or (ROOT / 'tmp').resolve() not in output.parents:
        raise ValueError('output must be fresh beneath repository tmp/')
    source = ROOT / 'palettes/penta_palettes_v097.yaml'
    source_bytes = source.read_bytes()
    document = yaml.safe_load(source_bytes)
    row = document['death_gameover_palette']['gameover_colors']
    encoded = b''.join(int(str(word), 16).to_bytes(2, 'little') for word in row)
    if encoded != gameover.NEW:
        raise ValueError('palette source differs from the reviewed color fix')
    document['death_gameover_palette']['gameover_colors'] = ['7FFF', '7FFF', '56B5', '294A']
    legacy_palette = ROOT / 'palettes/penta_palettes_restart_parent.yaml'
    if yaml.safe_load(legacy_palette.read_bytes()) != document:
        raise ValueError('historical source profile differs outside the explicit Game Over row')
    output.mkdir(parents=True)
    parent_output = output / 'restart-source'
    restart.build(parent_output, legacy_palette)
    parent = (parent_output / 'candidate.gb').read_bytes()
    restart.verify_receipt(parent_output / 'build-receipt.json', parent, legacy_palette)
    records = []
    stock_path = ROOT / 'rom/Penta Dragon (J).gb'
    stock = stock_path.read_bytes()
    reported = None
    stages = [('sara-atomic', sara, lambda data: sara.build(data)),
              ('secret-stock-graphics', graphics, lambda data: graphics.build(data, stock)),
              ('secret-palette-source', secret_palette, secret_palette.build),
              ('gameover-accent', gameover, gameover.build),
              ('native-projectile-templates', projectiles,
               lambda data: projectiles.build(data, stock)),
              ('continue-input-after-visuals', continuation,
               lambda data: continuation.build(data, after_visuals=True))]
    for name, module, transform in stages:
        result = transform(parent)
        records.append(dict(name=name, parent_sha256=digest(parent),
                            candidate_sha256=digest(result),
                            builder=str(Path(module.__file__).resolve()),
                            builder_sha256=digest(Path(module.__file__).read_bytes())))
        parent = result
        if name == 'sara-atomic':
            reported = result
    if presentation:
        parent, presentation_records = presentation_chain(parent, reported, release_lock)
        records.extend(presentation_records)
    if arena_alias:
        parent, arena_records = arena_alias_chain(parent, completion_safe=arena_completion_safe,
                                                  release_lock=release_lock)
        records.extend(arena_records)
    if secret_sound_alias:
        import build_secret_sound_alias_fast_trial as secret_alias
        result = secret_alias.build(parent)
        if digest(result) != PINS[release_lock]['secret_alias']:
            raise ValueError('secret alias chain differs from experimental pin')
        records.append(dict(name='secret-sound-alias-fast', parent_sha256=digest(parent),
                            candidate_sha256=digest(result),
                            builder=str(Path(secret_alias.__file__).resolve()),
                            builder_sha256=digest(Path(secret_alias.__file__).read_bytes())))
        parent = result
    if return_fade:
        parent,return_records=return_fade_chain(parent, release_lock)
        records.extend(return_records)
    if experimental_late_return_fade:
        parent, late_records = late_return_fade_chain(parent)
        records.extend(late_records)
    if source.read_bytes() != source_bytes:
        raise ValueError('palette source changed during construction')
    (output / 'candidate.gb').write_bytes(parent)
    receipt = dict(schema='penta-stream-regressions-source-v1',
                   candidate_sha256=digest(parent), original_sha256=digest(stock),
                   palette_source=str(source), palette_sha256=digest(source_bytes),
                   derived_parent_palette_sha256=digest(legacy_palette.read_bytes()),
                   historical_palette_change='only gameover_colors reset to exact gray parent before final purple overlay',
                   restart_receipt_sha256=digest((parent_output / 'build-receipt.json').read_bytes()),
                   stages=records, retained_candidate_inputs=False, release_qualified=False)
    # Includes transitive assembler/overlay helpers, not just direct imports.
    receipt['loaded_project_python_sources'] = {
        str(path.relative_to(ROOT)): digest(path.read_bytes())
        for module in tuple(sys.modules.values())
        if getattr(module, '__file__', None)
        for path in [Path(module.__file__).resolve()]
        if path.suffix == '.py' and ROOT in path.parents and path.is_file()
    }
    receipt['entrypoint_sha256'] = digest(Path(__file__).read_bytes())
    receipt['experimental_presentation_chain'] = presentation
    receipt['experimental_arena_alias_chain'] = arena_alias
    receipt['experimental_arena_completion_safe_chain'] = arena_completion_safe
    receipt['experimental_secret_sound_alias_chain'] = secret_sound_alias
    receipt['experimental_return_fade_chain'] = return_fade
    receipt['experimental_late_return_fade_chain'] = experimental_late_return_fade
    receipt['release_lock_chain'] = release_lock
    if release_lock:
        receipt['deferred_issues'] = [34]
    if secret_sound_alias:
        receipt['qualification_warning'] = 'Secret low-health audio comparison fails; experimental construction only, not deployment approval.'
    if return_fade:
        receipt['qualification_warning'] = 'Exact trial16 construction only. Bounded return audio passes do not qualify title timing, all routes or hardware; not deployment approval.'
    if experimental_late_return_fade:
        receipt['allocation_review_complete'] = False
        receipt['qualification_warning'] = (
            'Exact46eb experimental construction only. Fixed-ROM 00CF..00E0 allocation '
            'is not globally qualified; 414 full-route audio sample frames differ '
            'from the native-fade control. Broader routes and hardware remain '
            'unqualified; not deployment approval.')
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--presentation', action='store_true',
                        help='include the exact experimental presentation/star chain; not release promotion')
    parser.add_argument('--arena-alias', action='store_true',
                        help='with --presentation, include experimental #27 graphics-owner repair')
    parser.add_argument('--arena-completion-safe', action='store_true',
                        help='with --presentation --arena-alias, use direct scene resolution and preserve legacy completion; not release promotion')
    parser.add_argument('--secret-sound-alias', action='store_true',
                        help='requires all arena flags; experimental #26 low-health secret copier fix; audio NOT qualified')
    parser.add_argument('--return-fade', action='store_true',
                        help='requires all preceding chain flags; reproduce exact experimental return trial16, not release promotion')
    parser.add_argument('--experimental-late-return-fade', action='store_true',
                        help='requires --return-fade; reproduce46eb for offline testing; fixed-ROM allocation unqualified')
    parser.add_argument('--release-lock', action='store_true',
                        help='requires --return-fade; defer #14 and #34 with re-pinned downstream stages')
    args = parser.parse_args()
    print(json.dumps(build(args.output, presentation=args.presentation, arena_alias=args.arena_alias,
                           arena_completion_safe=args.arena_completion_safe,
                           secret_sound_alias=args.secret_sound_alias,
                           return_fade=args.return_fade,
                           experimental_late_return_fade=args.experimental_late_return_fade,
                           release_lock=args.release_lock), indent=2))
