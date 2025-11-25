def build_ips_patch(original: bytes, modified: bytes) -> bytes:
    if len(original) != len(modified):
        raise ValueError("IPS builder currently requires equal length ROMs (no trunc/extend).")
    records = []
    i = 0
    while i < len(original):
        if original[i] != modified[i]:
            start = i
            chunk = bytearray()
            while i < len(original) and original[i] != modified[i]:
                chunk.append(modified[i])
                i += 1
                if len(chunk) == 0xFFFF:  # IPS max block length
                    break
            # Record: 3-byte offset, 2-byte size, then data
            off = start
            size = len(chunk)
            records.append(off.to_bytes(3, "big") + size.to_bytes(2, "big") + bytes(chunk))
        else:
            i += 1
    out = bytearray(b"PATCH")
    for r in records:
        out.extend(r)
    out.extend(b"EOF")
    return bytes(out)
