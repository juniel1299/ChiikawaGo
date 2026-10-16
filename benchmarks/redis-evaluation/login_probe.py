# ruff: noqa: E501
# Literal SQL, synthetic URLs, and rendered table/SVG lines remain intact.
"""Synthetic failed-login burst only. Password stays in memory; no successful tokens."""

import concurrent.futures
import http.client
import json
import secrets
import subprocess
import time

from load import COMPOSE, ROOT, quantile

password = secrets.token_urlsafe(32)
code = "import sys; from apps.accounts.models import User; u=User.objects.get(email='perf@example.invalid'); u.set_password(sys.stdin.read()); u.save()"
subprocess.run(
    COMPOSE + ["exec", "-T", "api", "python", "manage.py", "shell", "-c", code],
    input=password,
    text=True,
    check=True,
    stdout=subprocess.DEVNULL,
)
body = json.dumps({"email": "perf@example.invalid", "password": secrets.token_urlsafe(32)})
for users in (1, 5, 10):
    for repeat in range(3):

        def request(_):
            c = http.client.HTTPConnection("127.0.0.1", 18080, timeout=30)
            start = time.monotonic()
            try:
                c.request(
                    "POST",
                    "/api/v1/auth/token",
                    body=body,
                    headers={"Content-Type": "application/json"},
                )
                r = c.getresponse()
                r.read()
                status = r.status
            except (OSError, http.client.HTTPException):
                status = 0
            finally:
                c.close()
            return {"status": status, "latency_ms": (time.monotonic() - start) * 1000}

        # Fixed number of requests avoids unbounded password-hash work.
        with concurrent.futures.ThreadPoolExecutor(max_workers=users) as pool:
            list(pool.map(request, range(users)))  # one warm-up per worker
            start = time.monotonic()
            rows = list(pool.map(request, range(30)))
            elapsed = time.monotonic() - start
        lat = [r["latency_ms"] for r in rows]
        result = {
            "concurrency": users,
            "repeat": repeat,
            "requests": 30,
            "elapsed_s": elapsed,
            "throughput": 30 / elapsed,
            "p50_ms": quantile(lat, 0.5),
            "p95_ms": quantile(lat, 0.95),
            "p99_ms": quantile(lat, 0.99),
            "status_counts": {
                str(s): sum(r["status"] == s for r in rows) for s in set(r["status"] for r in rows)
            },
            "raw": rows,
        }
        with (ROOT / "results" / "login-burst.jsonl").open("a") as f:
            f.write(json.dumps(result) + "\n")
        print({k: v for k, v in result.items() if k != "raw"}, flush=True)
