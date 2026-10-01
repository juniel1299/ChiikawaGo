import pytest
from drf_spectacular.generators import SchemaGenerator

pytestmark = pytest.mark.django_db


def test_token_success_responses_match_openapi(client, user):
    schema = SchemaGenerator().get_schema(request=None, public=True)
    login = client.post(
        "/api/v1/auth/token",
        {"email": user.email, "password": "Walking-in-the-park-42!"},
    )
    refresh = client.post("/api/v1/auth/token/refresh", {"refresh": login.data["refresh"]})
    for path, response in [("/api/v1/auth/token", login), ("/api/v1/auth/token/refresh", refresh)]:
        assert response.status_code == 200
        body = schema["paths"][path]["post"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        while "$ref" in body:
            body = schema["components"]["schemas"][body["$ref"].split("/")[-1]]
        assert body["type"] == "object"
        assert set(response.data) == set(body["properties"]) == {"access", "refresh"}
        assert set(body["required"]) == {"access", "refresh"}
        for field, value in response.data.items():
            assert isinstance(value, str)
            assert body["properties"][field]["type"] == "string"
