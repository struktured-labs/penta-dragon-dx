"""#45 narrow final-restore trace contract for the exact46eb trial layout."""


def failures(rows, backup, actual):
    errors=[]
    if len(rows)!=64:
        errors.append('expected exactly64 final restore writes')
    if any(r['port']!='FF69' or r['bank']!='14' for r in rows):
        errors.append('wrong restore port or code bank')
    if any(int(r['mode'])!=1 or not int(r['lcdc'],16)&0x80 for r in rows):
        errors.append('restore outside active-LCD VBlank')
    if [int(r['index'],16)&63 for r in rows]!=list(range(64)):
        errors.append('palette indices missing or out of order')
    values=bytes(int(r['value'],16) for r in rows)
    if len(backup)!=64 or values!=backup:
        errors.append('writes differ from palette backup')
    if actual!=backup:
        errors.append('resulting CRAM differs from palette backup')
    return errors
