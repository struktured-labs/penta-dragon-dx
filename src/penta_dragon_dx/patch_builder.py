def build_ips_patch(original: bytes, modified: bytes) -> bytes:
    if len(original) != len(modified):
        raise ValueError("IPS builder currently requires equal length ROMs (no trunc/extend).")
    if len(original) > 0x1000000:
        raise ValueError("IPS uses 24-bit offsets and cannot address ROMs larger than 16 MiB.")
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


def apply_ips_patch(original: bytes, patch: bytes) -> bytes:
    """Apply a standard IPS patch to an equal-length ROM image.

    Literal and RLE records are supported. A three-byte truncate/expand size
    after the EOF marker is deliberately rejected: the release builder emits
    equal-length Game Boy ROMs, so accepting a size-changing patch would hide
    a packaging error.
    """
    if not patch.startswith(b"PATCH"):
        raise ValueError("Invalid IPS header.")

    output = bytearray(original)
    cursor = 5
    while True:
        if cursor + 3 > len(patch):
            raise ValueError("Truncated IPS patch before EOF marker.")
        if patch[cursor:cursor + 3] == b"EOF":
            cursor += 3
            break

        offset = int.from_bytes(patch[cursor:cursor + 3], "big")
        cursor += 3
        if cursor + 2 > len(patch):
            raise ValueError("Truncated IPS record length.")
        size = int.from_bytes(patch[cursor:cursor + 2], "big")
        cursor += 2

        if size:
            if cursor + size > len(patch):
                raise ValueError("Truncated IPS literal record.")
            payload = patch[cursor:cursor + size]
            cursor += size
        else:
            if cursor + 3 > len(patch):
                raise ValueError("Truncated IPS RLE record.")
            run_length = int.from_bytes(patch[cursor:cursor + 2], "big")
            value = patch[cursor + 2]
            cursor += 3
            if run_length == 0:
                raise ValueError("IPS RLE record has zero length.")
            payload = bytes([value]) * run_length

        end = offset + len(payload)
        if end > len(output):
            raise ValueError(
                f"IPS record 0x{offset:06X}..0x{end:06X} exceeds "
                f"the {len(output)}-byte ROM."
            )
        output[offset:end] = payload

    if cursor != len(patch):
        raise ValueError(
            "Size-changing or trailing IPS data is not valid for this release."
        )
    return bytes(output)
