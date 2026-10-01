import json
import logging
import time
import uuid

logger = logging.getLogger("chii.requests")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        start = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
        match = getattr(request, "resolver_match", None)
        logger.info(
            json.dumps(
                {
                    "request_id": request.request_id,
                    "method": request.method,
                    "route": match.route if match else "unmatched",
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - start) * 1000, 2),
                }
            )
        )
        return response
