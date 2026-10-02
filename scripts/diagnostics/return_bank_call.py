"""#45 return-only call primitives; not a patched or qualified ROM.

Use the existing fixed 099D epilogue to fit an AF-preserving callback in six
bytes. The caller must be executing bank20; native calls return through 00C1.
Stack depth changes: callers inspecting their return stack need separate review.
"""

CALLBACK = 0x00C1
RESUME_BANK = 20
EPILOGUE = bytes.fromhex('CD6100 F1 C9')


def callback():
    return bytes((0xF5, 0x3E, RESUME_BANK, 0xC3, 0x9D, 0x09))


def native_call(address, bank=1):
    if not 0 <= address < 0x8000 or not 1 <= bank <= 0x7F:
        raise ValueError('native ROM address and supported bank required')
    # Entry stack: bank20 continuation. Three PUSH AF instructions reserve
    # callback, target and original AF without losing flags. Preserve HL while
    # filling the two synthetic return addresses. LD HL,SP+4 changes flags;
    # 099D restores the saved AF only after mapping the requested native bank.
    return bytes.fromhex('F5 F5 F5 E5 F804') + bytes((
        0x36, address & 255, 0x23, 0x36, address >> 8,
        0x23, 0x36, CALLBACK & 255, 0x23, 0x36, CALLBACK >> 8,
        0xE1, 0x3E, bank, 0xC3, 0x9D, 0x09))


def native_chain(addresses, bank=1):
    """Sequential native RET continuations, with one final bank20 callback.

    Not CALL-equivalent stack depth: use only reviewed callees. No cycle-parity
    claim. In particular a fade/wait chain must preload B before the fade.
    """
    addresses = tuple(addresses)
    if not addresses or len(addresses) > 8 or not 1 <= bank <= 0x7F:
        raise ValueError('one to eight native targets and supported bank required')
    if any(not 0 <= address < 0x8000 for address in addresses):
        raise ValueError('native ROM address required')
    targets = addresses + (CALLBACK,)
    result = bytearray([0xF5] * (len(targets) + 1))
    result.extend(bytes.fromhex('E5 F804'))
    for index, target in enumerate(targets):
        if index:
            result.append(0x23)
        result.extend((0x36, target & 255, 0x23, 0x36, target >> 8))
    result.extend((0xE1, 0x3E, bank, 0xC3, 0x9D, 0x09))
    return bytes(result)


def check_fixed_abi(rom):
    """Check required bytes, not a claim of all-scene allocation safety."""
    required = {
        0xC0: bytes.fromhex('C9') + bytes(7) + bytes.fromhex('F040 F680 E040 C9'),
        0x099D: EPILOGUE,
        0x0061: bytes.fromhex('EA09DC C3BE09'),
        0x09BE: bytes.fromhex('E099 EA0021 C9'),
    }
    for address, expected in required.items():
        if rom[address:address + len(expected)] != expected:
            raise ValueError(f'fixed ABI/preimage changed at {address:04X}')
