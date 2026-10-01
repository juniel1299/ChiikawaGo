import sys

from django.http import JsonResponse
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .error_logging import log_internal_exception


class Pagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


def error_body(code, message, details, request):
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": getattr(request, "request_id", None),
    }


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    request = context["request"]
    if response is None:
        log_internal_exception(exc, request)
        return Response(error_body("internal_error", "서버 오류가 발생했습니다.", {}, request), 500)
    codes = {
        400: "validation_error",
        401: "authentication_failed",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "rate_limited",
    }
    details = response.data
    message = (
        details.get("detail", "요청을 처리할 수 없습니다.")
        if isinstance(details, dict)
        else "잘못된 요청입니다."
    )
    response.data = error_body(
        codes.get(response.status_code, "request_error"), message, details, request
    )
    return response


def not_found(request, exception):
    return JsonResponse(
        error_body("not_found", "리소스를 찾을 수 없습니다.", {}, request), status=404
    )


def server_error(request):
    if (exc := sys.exc_info()[1]) is not None:
        log_internal_exception(exc, request)
    return JsonResponse(
        error_body("internal_error", "서버 오류가 발생했습니다.", {}, request), status=500
    )
