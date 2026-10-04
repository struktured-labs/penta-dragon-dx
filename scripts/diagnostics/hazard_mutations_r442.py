"""Closed-set, byte-exact negative controls for the reviewed r442 ROM."""
import hashlib

BASE_SHA = 'ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46'
CURRENT_R451C_SHA = 'b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892'
CURRENT_R453_SHA = '15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b'
CURRENT_R455_SHA = '6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9'
CURRENT_R456C_SHA = '8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4'
CURRENT_R456D_SHA = '69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722'
CURRENT_R527_SHA = '13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b'
CURRENT_R528_SHA = 'e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50'
CURRENT_R529_SHA = '5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208'
CURRENT_R530_SHA = '46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30'
CURRENT_R531_SHA = '9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855'
CURRENT_R532_SHA = '055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821'
CURRENT_R533_SHA = '4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba'
CURRENT_R534_SHA = '727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b'
CURRENT_R535_TILE_RETIRE_SHA = '681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3'
CURRENT_R535_STAGE_CARD_BLACK_SHA = 'fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576'
CURRENT_R536_PENTA_SEAM_SHA = "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350"
CURRENT_R535_STAGE1_ONLY_CARD_BLACK_SHA = 'b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96'
CURRENT_R536_STAGE1_ONLY_CARD_BLACK_SHA = 'ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63'


def mutants(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('mutation controls require exact r442')
    if source[0x77A8:0x77AC] != bytes.fromhex('CD 13 00 C9'):
        raise ValueError('shared close handoff changed')
    bank19 = 19 * 0x4000 - 0x4000
    right = bank19 + 0x61A5
    plans = {
        # Preserve CALL7798 and its scene0B invalidation handoff. Its tail
        # already clears FFE4; replace the redundant caller clear with the
        # deliberately unsafe full visible-map copy, on both close paths.
        'forced-visible-menu-repair': (
            (0x1B72, bytes.fromhex('AF E0 E4 C9'), bytes.fromhex('CD A0 42 C9')),
            (0x1DCB, bytes.fromhex('AF E0 E4 C9'), bytes.fromhex('CD A0 42 C9'))),
        'short-endpoint-span': ((bank19+0x62D4, b'\x0b', b'\x0a'),),
        'missing-alternate-phase': ((bank19+0x62CB, bytes.fromhex('9E 6D'), bytes.fromhex('F6 61')),),
        'short-right-endpoint-span': ((right, b'\x0a', b'\x09'),),
    }
    result = {}
    for name, patches in plans.items():
        rom = bytearray(source)
        for offset, old, new in patches:
            if source[offset:offset+len(old)] != old or len(old) != len(new):
                raise ValueError('mutation preimage mismatch')
            rom[offset:offset+len(old)] = new
        # Header checksum remains valid: none of these changes touch0134..014C.
        checksum = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
        rom[0x14E:0x150] = checksum.to_bytes(2, 'big')
        result[name] = bytes(rom)
    return result


def authenticate(source, changed):
    source_sha = hashlib.sha256(source).hexdigest()
    if source_sha in {CURRENT_R451C_SHA, CURRENT_R453_SHA, CURRENT_R455_SHA, CURRENT_R456C_SHA, CURRENT_R456D_SHA, CURRENT_R527_SHA, CURRENT_R528_SHA, CURRENT_R529_SHA, CURRENT_R530_SHA, CURRENT_R531_SHA, CURRENT_R532_SHA, CURRENT_R533_SHA, CURRENT_R534_SHA, CURRENT_R535_TILE_RETIRE_SHA, CURRENT_R535_STAGE_CARD_BLACK_SHA, CURRENT_R536_PENTA_SEAM_SHA, "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b", "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d", "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5", CURRENT_R535_STAGE1_ONLY_CARD_BLACK_SHA, CURRENT_R536_STAGE1_ONLY_CARD_BLACK_SHA,
                      # Release lock: 1B72/1DCB and all of bank 19 are outside
                      # the release-lock delta (release_lock_lineage).
                      "93d21c4e00d2565c9bb9423de77d90f1e7b5b986b5633c53000d6e13c80e62fe"}:
        plans = {
            'forced-visible-menu-repair': ((0x1B72, bytes.fromhex('AF E0 E4 C9'), bytes.fromhex('CD A0 42 C9')),
                                           (0x1DCB, bytes.fromhex('AF E0 E4 C9'), bytes.fromhex('CD A0 42 C9'))),
            'short-endpoint-span': ((19 * 0x4000 - 0x4000 + 0x62D4, b'\x0b', b'\x0a'),),
            'missing-alternate-phase': ((19 * 0x4000 - 0x4000 + 0x62CB, bytes.fromhex('9E 6D'), bytes.fromhex('F6 61')) ,),
            'short-right-endpoint-span': ((19 * 0x4000 - 0x4000 + 0x61A5, b'\x0a', b'\x09'),),
        }
        matches = []
        for name, patches in plans.items():
            rom = bytearray(source)
            for offset, old, new in patches:
                if source[offset:offset + len(old)] != old:
                    raise ValueError('mutation preimage mismatch')
                rom[offset:offset + len(old)] = new
            value = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
            rom[0x14E:0x150] = value.to_bytes(2, 'big')
            if bytes(rom) == changed:
                matches.append(name)
    else:
        matches = [name for name, payload in mutants(source).items() if payload == changed]
    if len(matches) != 1:
        raise ValueError('not an exact approved hazard negative control')
    return matches[0]
