"""#34 bounded raw-to-edge delivery oracle; not all-phase/gameplay qualification."""


def assess(rows, start, hold, maximum_latency=12):
    if hold < 1 or maximum_latency < hold:
        raise ValueError('positive hold and sufficient observation window required')
    end = start + maximum_latency
    window = [r for r in rows if start - 1 <= int(r['frame']) <= end]
    failures = []
    raw = [r for r in window if r['address'] == 'FF93']
    if [int(r['frame']) for r in raw] != list(range(start - 1, end + 1)):
        failures.append('missing, repeated, or unordered raw input samples')
    for row in raw:
        expected = 4 if start <= int(row['frame']) < start + hold else 0
        if int(row['value'], 16) != expected:
            failures.append('raw input differs from the requested isolated pulse')
            break
    polls = [r for r in window if r['address'] == 'FF94'
             and int(r['frame']) >= start]
    delivered = [r for r in polls if int(r['value'], 16) & 4]
    if not polls:
        failures.append('missing native gameplay edge observations')
    if len(delivered) != 1:
        failures.append('Select must be delivered exactly once in the bounded window')
    after_release = []
    for row in delivered:
        if int(row['frame']) >= start + hold:
            if int(row['raw'], 16) & 4 or int(row['held'], 16) & 4:
                failures.append('post-release delivery has sticky raw or held Select')
            else:
                after_release.append(int(row['frame']))
    return dict(status='FAIL' if failures else 'PASS', failures=failures,
                delivered_frames=[int(r['frame']) for r in delivered],
                post_release_frames=after_release,
                scope=__doc__, start=start, hold=hold, observed_through=end)
