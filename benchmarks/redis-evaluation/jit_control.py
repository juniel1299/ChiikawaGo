"""Change only the isolated performance database's JIT default."""

import argparse
import subprocess

from load import COMPOSE

p = argparse.ArgumentParser()
p.add_argument("mode", choices=["off", "reset"])
a = p.parse_args()
sql = (
    "ALTER DATABASE chii_perf SET jit=off"
    if a.mode == "off"
    else "ALTER DATABASE chii_perf RESET jit"
)
subprocess.run(
    COMPOSE
    + [
        "exec",
        "-T",
        "db",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "perf",
        "-d",
        "chii_perf",
        "-c",
        sql,
    ],
    check=True,
)
subprocess.run(
    COMPOSE + ["exec", "-T", "db", "psql", "-U", "perf", "-d", "chii_perf", "-Atc", "SHOW jit"],
    check=True,
)
