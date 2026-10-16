"""Check completeness and sanitize guarantees before publishing the report."""

import collections
import hashlib
import json
import pathlib

from load import quantile

root = pathlib.Path(__file__).resolve().parent / "results"
expected = {
    "baseline-1x": 48,
    "baseline-10x": 48,
    "jit-off-10x": 18,
    "jit-restored-10x": 6,
    "fixed-arrival-10x": 9,
    "concurrency-confirmation-10x": 18,
}


def key(r):
    return tuple(r[k] for k in ("scenario", "concurrency", "repeat", "arrival_rate"))


report = {}
for name, n in expected.items():
    summaries = [json.loads(line) for line in (root / f"{name}.jsonl").read_text().splitlines()]
    assert len(summaries) == n, (name, len(summaries), n)
    assert len({key(r) for r in summaries}) == n
    records = collections.defaultdict(list)
    for line in (root / f"{name}-requests.jsonl").read_text().splitlines():
        r = json.loads(line)
        records[key(r)].append(r)
    for m in summaries:
        rs = records[key(m)]
        assert len(rs) == m["requests"], (name, key(m))
        assert sum(r["status"] == 200 for r in rs) == m["success"]
        assert abs(quantile([r["latency_ms"] for r in rs], 0.95) - m["p95_ms"]) < 0.001
    report[name] = {
        "trials": n,
        "requests": sum(len(r) for r in records.values()),
        "non_200": sum(r["status"] != 200 for rows in records.values() for r in rows),
    }
login = [json.loads(line) for line in (root / "login-burst.jsonl").read_text().splitlines()]
assert len(login) == 9 and all(len(r["raw"]) == 30 for r in login)
report["login"] = {"trials": 9, "requests": 270}
for f in root.glob("*.json*"):
    text = f.read_text().lower()
    for marker in [
        '"password"',
        '"authorization"',
        '"access"',
        '"refresh"',
        '"latitude"',
        '"longitude"',
        "bearer ",
        "/users/",
        "0101000020",
    ]:
        assert marker not in text, (f.name, marker)
manifest = {
    f.name: hashlib.sha256(f.read_bytes()).hexdigest()
    for f in sorted(root.glob("*.json*"))
    if f.name not in ["validation.json", "manifest.json"]
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2))
(root / "validation.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
