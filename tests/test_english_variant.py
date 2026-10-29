import importlib.util, pathlib

spec = importlib.util.spec_from_file_location(
    'bev', pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'build_english_variant.py')
bev = importlib.util.module_from_spec(spec); spec.loader.exec_module(bev)


def test_script_encoding():
    assert bev.script('MOTHER') == bytes.fromhex('17191e120f1c')
    assert bev.script('a b.') == bytes([0x25, 0x00, 0x26, 0x54])


def test_credit_fits_fill():
    assert len(bev.CREDIT) == 90
    assert bev.SCRIPT_END_FILE + len(bev.CREDIT) < bev.NOISE_END_FILE
    for name in (b'Hiryuu', b'Tyrome', b'Kero'):
        assert bev.script(name.decode()) in bev.CREDIT
