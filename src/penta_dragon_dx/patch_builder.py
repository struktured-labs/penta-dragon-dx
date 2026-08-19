def build_ips_patch(original: bytes, modified: bytes) -> bytes:
    if len(modified) < len(original):
        raise ValueError("IPS builder does not truncate ROMs.")
    if len(modified) > 0x1000000:
        raise ValueError("IPS uses 24-bit offsets and cannot address ROMs larger than 16 MiB.")
    records = []
    i = 0
    while i < len(modified):
        differs = i >= len(original) or original[i] != modified[i]
        if differs:
            start = i
            chunk = bytearray()
            while i < len(modified) and (
                i >= len(original) or original[i] != modified[i]
            ):
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
    """Apply a standard literal/RLE IPS patch, including ROM expansion.

    Records beyond the input end extend the image. The release builder writes
    every extension byte explicitly, so reconstruction never depends on a
    patcher's choice of gap-fill value. A three-byte truncate size after EOF
    remains rejected because release images never shrink.
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
            output.extend(bytes(end - len(output)))
        output[offset:end] = payload

    if cursor != len(patch):
        raise ValueError(
            "Size-changing or trailing IPS data is not valid for this release."
        )
    return bytes(output)
