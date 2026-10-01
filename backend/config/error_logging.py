"""Exception diagnostics without exception values, source lines, or local variables."""

import json
import logging
import traceback

from psycopg import Error as PsycopgError

logger = logging.getLogger("chii.errors")
SQLSTATE_MESSAGES = {
    "23503": "Database foreign key constraint violation",
    "23505": "Database unique constraint violation",
    "40001": "Database serialization failure",
    "40P01": "Database deadlock detected",
}


def log_internal_exception(exc, request):
    chain = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        message = "Internal exception; original message withheld"
        if isinstance(exc, PsycopgError):
            message = SQLSTATE_MESSAGES.get(exc.sqlstate, "Database exception; details withheld")
        chain.append(
            {
                "exception_type": type(exc).__name__,
                "exception_message": message,
                "stack_trace": [
                    {
                        "file": frame.f_code.co_filename,
                        "function": frame.f_code.co_name,
                        "line": line,
                    }
                    for frame, line in traceback.walk_tb(exc.__traceback__)
                ],
            }
        )
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    logger.error(
        json.dumps(
            {
                "request_id": getattr(request, "request_id", None),
                **chain[0],
                "chained_exceptions": chain[1:],
            }
        )
    )
