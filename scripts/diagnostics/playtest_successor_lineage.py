"""#54/#60 successor identity for unchanged component contracts, not readiness.

Every changed run from played ffc to combined6c4a9654 is explicit. Authenticate
both complete images and require the caller's component spans to be unchanged.
Never use the reconstructed parent for rendering, gameplay, or acceptance runs.
"""
import hashlib

PARENT_SHA = "ffc29f4e29f2c2f9995f132c08676624ad92a206b822b3afdf835be3ad072feb"
CANDIDATE_SHA = "6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228"
RUNS = (
    (0x14e, "23b8", "d8f3"),
    (0x1a2f, "21c2ffaf0604220520fc21b2ffaf0605220520fc3e01e0dae0e4", "21c2ffaf0604220520fc2eb20605220520fc3e01e091e0dae0e4"),
    (0x7569, "cd7e00cd2b49", "3e3fcd610000"),
    (0x7589, "cd470fcda8", "3e3fcd6100"),
    (0x758f, "e60128f9afe095e094", "000000000000000000"),
    (0x7b91, "cda17b119bff061d7e1223130520f9c96f2600295d54291929291919d711b37b19", "fe07d27e7c5f87836f7bcb37879521b37bd7b7119bff061d2a12130520facd887c"),
    (0x7c7e, "704eac7c243f3f3f3f4041424344454647ef", "f53e3fcd6100f1c90000c5060e0520fdc1c9"),
    (0x37dac, "10", "0f"),
    (0x37db3, "06203eff220520fc06103e03220520fc06103e05220520fc06103e04220520fc06103e05220520fc06103e", "3e032206203eff220520fc06103e03220520fc06103e05220520fc06103e04220520fc06103e05220520fc"),
    (0x37ddf, "220520fc067f3e04220520fc06013e00220520fc", "103e06220520fc067f3e04220520fc3e0022f5f1"),
    (0x43dac, "10", "0f"),
    (0x43db3, "06203eff220520fc06103e03220520fc06103e05220520fc06103e04220520fc06103e05220520fc06103e", "3e032206203eff220520fc06103e03220520fc06103e05220520fc06103e04220520fc06103e05220520fc"),
    (0x43ddf, "220520fc067f3e04220520fc06013e00220520fc", "103e06220520fc067f3e04220520fc3e0022f5f1"),
    (0xfc000, "ffffffffffffffffffffff", "f1cd0042f511b3331911b8"),
    (0xfc00c, "ffffffffff", "3e01c3817c"),
    (0xfc06f, "ffffffffffffffffffffffffffffffffffffffffffffff", "f5afe0d47dfed42003cd0045f0d4fe0420faafe0d4f1c9"),
    (0xfc200, "ffffffffff", "cda049119b"),
    (0xfc206, "ffffffffffffffffffff", "061d7e1223130520f9c9"),
    (0xfc300, "ffffffffffffffffff", "cd7e00cd2043f3cd80"),
    (0xfc30a, "ffffffffffff", "fb3e01c36b75"),
    (0xfc320, "ffffffffffffffffffffffffffffffffffffffffffffffffff", "e5c5f5f306a02100c0cda20906a02100c1cda209fbf1c1e1c9"),
    (0xfc400, "ffffffffffffffffffffffffffffffff", "00000000000000000000000000000000"),
    (0xfc500, "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "f5c5d5e5f04ff53e01e04f2100981110000640f33e44e051afe0527ce0537de054f041e60220faafe055fb190520e4f1e04fe1d1c1f1c9"),
    (0xfc600, "ffffffffffffffffffffffffffffffffffffffff", "cd470fcda800e60128f9afe095e0943e01c39575"),
    (0xfc800, "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "4040006026868d8c8d101112131415161700403c0020070000000000025042bc64224849496508090a0b0c0d0e0fc843a003e0030100910000036044fc682e6970707000010203040506073f46500050070000000000047047bc6c183232323218191a1b1c1d0203424c500050070000000000054049447008212121211e1f202122232425f24c60001007000000000006504ac47410373f3e3e262728292a2b2425fd4d50005007000000000007604d2c78152f2f2f2f2c2d2e2f30313233105060009006000000000008704eac7c243f3f3f3f4041424344454647ef5000000000000000000009704eac7c243f3f3f3f48494a4b44454647ef5000000000000000000009"),
    (0xfc9a0, "ffffffffffffffffffffffffffffffffffff", "6f2600295d54291929291919d711004819c9"),
    (0xff56b, "ffffffffffff", "cd6100c30043"),
    (0xff58e, "ffffff", "c30046"),
    (0xff595, "ffffff", "cd6100"),
    (0xffc81, "ffffffffffff", "cd6100c30040"),
)

def is_candidate(rom):
    import lowhealth_candidate_lineage
    return (len(rom) == 0x100000 and hashlib.sha256(rom).hexdigest() == CANDIDATE_SHA
            or lowhealth_candidate_lineage.is_candidate(rom))

def authenticated_parent(rom, *ranges):
    import lowhealth_candidate_lineage
    if lowhealth_candidate_lineage.is_candidate(rom):
        rom = lowhealth_candidate_lineage.authenticated_parent(rom, *ranges)
    if not is_candidate(rom):
        raise ValueError("not the exact playtest successor")
    if not ranges:
        raise ValueError("explicit component ranges required")
    for start, end in ranges:
        if not 0 <= start < end <= len(rom):
            raise ValueError("invalid component range")
        if any(start < offset + len(bytes.fromhex(after)) and offset < end
               for offset, before, after in RUNS):
            raise ValueError("component intersects successor delta")
    parent = bytearray(rom)
    previous_end = 0
    for offset, before_hex, after_hex in RUNS:
        before, after = bytes.fromhex(before_hex), bytes.fromhex(after_hex)
        if len(before) != len(after) or offset < previous_end:
            raise ValueError("invalid delta table")
        if parent[offset:offset+len(after)] != after:
            raise ValueError("successor delta bytes differ")
        parent[offset:offset+len(before)] = before
        previous_end = offset+len(after)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA:
        raise ValueError("ancestor reconstruction failed")
    return bytes(parent)
