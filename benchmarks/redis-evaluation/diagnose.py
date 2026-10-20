# ruff: noqa: B023
# Each iteration completes and joins all callbacks before loop variables change.
# ruff: noqa: E402
# Django must initialize before importing app models.
"""Sequential in-process diagnostics; not additive to HTTP latency or a load test."""

import json
import os
import pathlib
import sys
import time
from unittest.mock import patch

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
import django

django.setup()
import logging

logging.getLogger("chii.requests").disabled = True
from django.db import connection
from django.db.backends.base.base import BaseDatabaseWrapper
from rest_framework.serializers import ListSerializer
from rest_framework.test import APIClient
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User

sys.path.insert(0, "/perf")
from load import SCENARIOS

assert connection.settings_dict["NAME"] == "chii_perf"
scale = int(os.environ.get("PERF_SCALE", "1"))
label = os.environ.get("PERF_LABEL", "baseline")
result = {}
plans = {}
repetitions = int(os.environ.get("PERF_DIAG_SAMPLES", "30"))
warmups = 5
auth_original = JWTAuthentication.authenticate
serialize_original = ListSerializer.to_representation
connect_original = BaseDatabaseWrapper.connect
for name, (path, authenticated) in SCENARIOS.items():
    if name == "nearby_moving":
        continue
    rows = []
    captured = []
    for i in range(warmups + repetitions):
        connection.close()
        client = APIClient()
        # Token generation excluded from timing; no DB RefreshToken side effects.
        if authenticated:
            t = AccessToken()
            t["user_id"] = str(User.objects.get(email="perf@example.invalid").pk)
            client.credentials(HTTP_AUTHORIZATION="Bearer " + str(t))
        connection.close()
        metrics = {
            "auth_ms": 0,
            "connection_ms": 0,
            "serialization_ms": 0,
            "serialization_excluding_sql_ms": 0,
            "sql": [],
        }

        def auth(self, request):
            start = time.perf_counter()
            try:
                return auth_original(self, request)
            finally:
                metrics["auth_ms"] += (time.perf_counter() - start) * 1000

        def connect(self):
            start = time.perf_counter()
            try:
                return connect_original(self)
            finally:
                metrics["connection_ms"] += (time.perf_counter() - start) * 1000

        def serialize(self, data):
            start = time.perf_counter()
            sql_before = sum(q["ms"] for q in metrics["sql"])
            try:
                return serialize_original(self, data)
            finally:
                duration = (time.perf_counter() - start) * 1000
                metrics["serialization_ms"] += duration
                metrics["serialization_excluding_sql_ms"] += duration - (
                    sum(q["ms"] for q in metrics["sql"]) - sql_before
                )

        def sql(execute, query, params, many, context):
            start = time.perf_counter()
            try:
                return execute(query, params, many, context)
            finally:
                kind = (
                    "auth"
                    if "accounts_user" in query
                    else ("count" if "COUNT(" in query else "page")
                )
                metrics["sql"].append({"kind": kind, "ms": (time.perf_counter() - start) * 1000})
                if i == warmups + repetitions - 1 and kind != "auth":
                    captured.append((kind, query, params))

        start = time.perf_counter()
        with (
            patch.object(BaseDatabaseWrapper, "connect", connect),
            patch.object(JWTAuthentication, "authenticate", auth),
            patch.object(ListSerializer, "to_representation", serialize),
            connection.execute_wrapper(sql),
        ):
            r = client.get(path)
        metrics["total_ms"] = (time.perf_counter() - start) * 1000
        metrics["status"] = r.status_code
        if i >= warmups:
            rows.append(metrics)
    result[name] = rows

    def sanitize(obj):
        if isinstance(obj, list):
            return [sanitize(x) for x in obj]
        if isinstance(obj, dict):
            return {
                k: (
                    "[redacted expression]"
                    if k
                    in [
                        "Filter",
                        "Index Cond",
                        "Recheck Cond",
                        "Hash Cond",
                        "Merge Cond",
                        "Join Filter",
                        "Sort Key",
                        "Output",
                    ]
                    else sanitize(v)
                )
                for k, v in obj.items()
            }
        return obj

    plans[name] = []
    with connection.cursor() as c:
        for kind, query, params in captured:
            c.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, params)
            plans[name].append({"kind": kind, "plan": sanitize(c.fetchone()[0])})
pathlib.Path(f"/perf/results/{label}-{scale}x-diagnostics.json").write_text(
    json.dumps(
        {"warmups": warmups, "repetitions": repetitions, "samples": result, "plans": plans},
        indent=2,
    )
)
print("Diagnostics saved without SQL parameters or request payloads.")
