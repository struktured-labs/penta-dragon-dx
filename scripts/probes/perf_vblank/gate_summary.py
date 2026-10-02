import json,sys
for p in sys.argv[1:]:
    t=open(p).read(); d=json.loads(t[t.find("{"):])
    m=d.get("metric",{}); ps=m.get("per_seed",{})
    us=[k for k,v in ps.items() if v.get("usable")]
    print(p.split("/")[-3], d.get("status"), "ratio=%.4f"%m["throughput_ratio_by_replay"]["a"], f"usable={len(us)}/{len(ps)}", "fails=",[f for f in (d.get("failures") or [])][:3])
