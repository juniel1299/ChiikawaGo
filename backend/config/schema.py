def add_error_responses(result, generator, request, public):
    """Document the same error envelope returned by the DRF exception handler."""
    result.setdefault("components", {}).setdefault("schemas", {})["ApiError"] = {
        "type": "object",
        "required": ["error", "request_id"],
        "properties": {
            "error": {
                "type": "object",
                "required": ["code", "message", "details"],
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {},
                },
            },
            "request_id": {"type": "string", "format": "uuid"},
        },
    }
    for path in result["paths"].values():
        for method, operation in path.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            statuses = ["400", "401", "403", "404", "405", "500"]
            if operation.get("operationId", "").startswith(
                ("batch_", "notifications_")
            ) or operation.get("operationId") in {"encounters_create", "encounters_capture"}:
                statuses.append("409")
            for status in statuses:
                operation["responses"].setdefault(
                    status,
                    {
                        "description": "API error envelope; details depend on the error code.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ApiError"}
                            }
                        },
                    },
                )
    return result
