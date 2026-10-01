"""#34 scoped replay ownership checks, not an all-scene RAM allocation proof."""
SITES = {('DF81', '6CAE'), ('DF82', '6CB2'),
         ('DF81', '6DA5'), ('DF82', '6DA9')}


def failures(rows):
    errors = []
    observed = {(r['address'], r['pc']) for r in rows}
    if observed != SITES:
        errors.append('missing or foreign buffer writer sites')
    for r in rows:
        if r['bank'] != '25' or int(r['svbk'], 16) & 7 != 7:
            errors.append('wrong ROM or physical WRAM bank')
        if r['ie'] != '00':
            errors.append('interrupts enabled during mapped-buffer write')
        allowed = {'00', '04'} if r['address'] == 'DF81' else {'00', '0C'}
        if r['value'] not in allowed:
            errors.append('unexpected pending or Shalamar owner value')
    values = {(r['address'], r['value']) for r in rows}
    if not {('DF81','04'), ('DF81','00'), ('DF82','0C'), ('DF82','00')} <= values:
        errors.append('capture lacks a press, consumption, or inactive owner')
    return sorted(set(errors))
