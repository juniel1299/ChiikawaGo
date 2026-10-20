# Phase 11: Redis necessity evaluation

This directory contains an isolated, synthetic measurement harness, not application features.
No Redis dependency, cache backend, crawler invocation or production-data mutation is included.
Results describe local Django runserver + Docker Desktop + emulated amd64 PostGIS only.
They are **not production capacity estimates**.

## Fixed protocol

- Baseline commit: `f9363d265e46afef6233efe994e57507c3116330`.
- Seed: `20261016`; deterministic UUID5 identifiers and Python PRNG.
- Scale 1: 10,000 Spots, 100 Characters, 500 Variants, 10,000 published News.
- Scale 10: exactly ten times those counts. Counts are hypotheses, not forecast traffic/data.
- Spots: 50% dense square, 30% regional square, 20% sparse square; 10% inactive.
- News: four categories equally distributed; paired publication timestamps; empty summaries.
- One synthetic user; JWT generated outside each HTTP trial and retained only in memory.
- API and DB: each capped at 2 CPUs / 2 GiB. Only these two containers run.
- Default closed-loop matrix: 8 scenarios × 2 concurrency levels (1, 5) × 3 repetitions × 2 scales.
- Each trial: at least 2 seconds warm-up, **drain all warm-up requests**, then 8 seconds of request starts, drain, record.
- Throughput = successful measured requests / actual measurement time including drain.
- Percentiles: nearest rank on pooled measured requests; also preserve each trial's percentiles.
- Short trials explore the matrix. Tail percentiles with small sample sizes are descriptive only.
- `open_load.py`: fixed arrivals, 3-second warm-up drained, 30-second measured arrival window, 3 repeats, maximum 50 request workers. Includes scheduling/queue delay in latency and drains all scheduled requests.
- CPU/connection sampling approximately every 3 seconds (docker stats collection plus 1-second pause), includes warm-up and drain; lock observations are sampled, not proof that no transient wait occurred.
- Docker CPU 100% means one core; 2 CPU quotas allow about 200%, with sampling variation.
- Diagnostics are separate sequential, in-process APIClient runs: 5 warm-up + 30 measured requests per scenario, fresh Django DB connection per request. They do not add up to concurrently loaded HTTP percentiles.
- Authentication includes its user lookup/connection work. SQL timings overlap auth; serialization may include lazy QuerySet execution. Do not sum these overlapping timers.
- EXPLAIN ANALYZE uses the same SQL/parameters internally but stores only sanitized JSON plans, without expressions/coordinates.

## Reproduce

Run from the repository root. Existing backend image must have been built from the baseline lockfile.

```sh
docker build -t chii-world-api backend
docker compose -f benchmarks/redis-evaluation/compose.yaml up -d --wait
docker compose -f benchmarks/redis-evaluation/compose.yaml exec -T api python manage.py migrate --noinput
docker compose -f benchmarks/redis-evaluation/compose.yaml exec -T api python /perf/seed.py
python3 benchmarks/redis-evaluation/load.py --scale 1
docker compose -f benchmarks/redis-evaluation/compose.yaml exec -T api python /perf/diagnose.py
docker compose -f benchmarks/redis-evaluation/compose.yaml exec -T -e PERF_SCALE=10 api python /perf/seed.py
python3 benchmarks/redis-evaluation/load.py --scale 10
docker compose -f benchmarks/redis-evaluation/compose.yaml exec -T -e PERF_SCALE=10 -e PERF_DIAG_SAMPLES=10 api python /perf/diagnose.py
python3 benchmarks/redis-evaluation/summarize.py
```

The seeder refuses databases other than `chii_perf`. It replaces only synthetic catalog/news/spot data there. The dedicated `chii-perf` project/volume must never be pointed at a development or production DB. No Worker or Scheduler is started; Sources are inactive.

Load results append by design. Archive/move an existing run's results before reproducing; do not combine runs with different hardware/settings under the same label. The host port is localhost-only 18080. The network uses a normal Docker bridge because Docker Desktop did not publish the API port on an internal-only network. No harness code invokes external URLs.

The first short-window pilot used a different warm-up accounting method and is stored separately as `pilot-short-window-*`. It is excluded from `summary.*` and final baseline comparisons. An earlier connection-preflight failure was discarded, not counted as API load.

## Safe results

Raw records contain scenario/key IDs, status, timing and resource counts. They contain no URL query strings, coordinates, passwords, JWTs, request bodies or response bodies. Synthetic coordinates appear only in the generator source. Fixed Compose values are isolated test credentials, not secrets. Do not use them in deployed environments.

`login_probe.py` assigns a random in-memory password to the synthetic user, sends a different random password, stores only timings/status, and never records either value. Login results describe invalid credentials (401), not infrastructure errors. A finite 30 requests per repetition bounds password hashing work.

Changes under evaluation must be one at a time, after baseline + diagnostics, on this isolated DB/configuration. Preserve before/after raw files and rerun the same measurement conditions. No production optimization is implied by a local result.

## Completion protocol and isolated JIT experiment

The interrupted 10x overload run is retained as `pilot-interrupted-overload-*` and excluded. Client timeouts may leave server work in progress, so the completed harness waits for zero active database requests (up to 120 seconds) before each trial, after warm-up drain, and after each trial. Activity counts include PostgreSQL parallel workers, not just client connections. The original 1x run had no timeouts and is retained; 1x and 10x took place in different sessions. Do not interpret all differences as a pure scale effect, especially noisy 1x News samples.

Diagnostics: 1x uses 5 warm-up + 30 measured samples; 10x uses 5 + 10, recorded in its JSON. All diagnostic calls deliberately use fresh DB connections. They expose connection/startup versus warm EXPLAIN costs, but are not production latency estimates.

The initial connection-reuse experiment was not executed: Django documents that runserver threading negates persistent-connection effectiveness. No `CONN_MAX_AGE` change was applied. Instead, observed JIT costs justify a single-variable `jit=off` comparison on the isolated database:

```sh
python3 benchmarks/redis-evaluation/jit_control.py off
python3 benchmarks/redis-evaluation/load.py --scale 10 --label jit-off --scenarios nearby_wide nearby_dense news
docker compose -f benchmarks/redis-evaluation/compose.yaml exec -T -e PERF_SCALE=10 -e PERF_LABEL=jit-off -e PERF_DIAG_SAMPLES=10 api python /perf/diagnose.py
python3 benchmarks/redis-evaluation/jit_control.py reset
python3 benchmarks/redis-evaluation/load.py --scale 10 --label jit-restored --scenarios nearby_wide
python3 benchmarks/redis-evaluation/open_load.py --scale 10 --rates 1 3 5
python3 benchmarks/redis-evaluation/login_probe.py
python3 benchmarks/redis-evaluation/summarize.py
python3 benchmarks/redis-evaluation/report.py
python3 benchmarks/redis-evaluation/plot.py
```

JIT changes neither API semantics nor application files and is reset afterward. Query/index/HTTP caching recommendations that were not experimentally changed must not be described as measured improvements. The fixed-arrival test opens a fresh HTTP connection per request; it is a separate workload from closed-loop persistent HTTP clients.

For short 8-second trials, 10/30/60-second reuse windows cannot establish an optimal TTL. Fixed endpoints and continuously moving endpoints are synthetic bounds, not estimates of real user cache hit rates. Fixed-arrival runs cover 30 seconds; no real traffic trace is available.


Additional concurrency confirmation (JIT reset before execution):

```sh
python3 benchmarks/redis-evaluation/load.py --scale 10 --label concurrency-confirmation --scenarios characters news --concurrency 10 25
python3 benchmarks/redis-evaluation/load.py --scale 10 --label concurrency-confirmation --scenarios nearby_dense --concurrency 2 10
python3 benchmarks/redis-evaluation/validate_results.py
docker compose -f benchmarks/redis-evaluation/compose.yaml stop
```

The completed overload run exposed the default 64 MiB Docker `/dev/shm` limit. It is intentionally not increased in this baseline. `overload-diagnosis.json` contains fixed error-pattern counts only, aggregated over container lifetime including warm-ups/pilots. No raw server log or SQL is preserved. Status `0` denotes a client transport/timeout failure; it is not an HTTP response code. Percentiles including these failures are deadline-censored observations. `summary.*` also provides status counts and successful-response-only p95.

The 147 HTTP trials contain 13,343 measured requests; 9 login trials contain 270. `validation.json` checks trial/sample consistency and `manifest.json` hashes raw/derived JSON files. The data footprint is about 3.6 MiB, deliberately retained as evidence. Temporary bytecode/cache directories are ignored and not part of the report. No service code changed, so existing functional test results were not rerun or relabeled as new test passes.


## Git artifact policy (Phase 11 checkpoint)

Commit only scripts, this isolated Compose definition, README/REPORT/RESULTS, and the
small allowlisted aggregates/environment/validation JSON and CSV in `results/`.
Per-request/trial JSONL, detailed diagnostic plans, excluded pilots, generated charts,
and the raw-file hash manifest remain local and are ignored by Git. The raw data has
not been deleted. Server execution logs, database volumes, bytecode and build output
are not committed.

A fresh checkout contains the completed RESULTS table and aggregate evidence, not
individual historical samples. To regenerate summary/diagnostics/charts or run
`validate_results.py`, first execute the complete measurement protocol to produce
local raw files. The committed validation.json records the original full-data check;
it is not a claim that a fresh checkout contains those raw files. Archive existing
local results before a rerun; append-mode files must not mix runs.
