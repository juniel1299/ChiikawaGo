# REST API 규약

## 기본 규칙

- `/api/v1`, trailing slash 없음. Admin `/admin/`은 Django 기본 규약을 따른다.
- JSON snake_case, 시간 ISO 8601 UTC, 거리 단위 m.
- 직접 API 인증은 `Authorization: Bearer <access_token>`.
- 단건은 객체 그대로, 목록은 `{count, next, previous, results}`. 기본 20개, page_size 최대 100.
- `page`는 페이지 번호, `page_size`는 DRF PageNumberPagination 규칙을 사용한다. 초과 page_size는 100으로 제한, 잘못된 page는 404.
- HTTP 201 생성, 200 조회/동작, 204 본문 없는 완료, 400 입력 오류, 401 인증 실패, 403 권한 부족, 404 미존재, 405 미지원 메서드, 500 내부 오류.
- 409 상태 충돌, 429 요청 제한은 해당 기능 도입 시 사용한다.
- 초기 API는 모든 응답 `Cache-Control: no-store`. 공유 캐시는 도입하지 않는다.

오류 형식:

```json
{
  "error": {
    "code": "validation_error",
    "message": "요청을 처리할 수 없습니다.",
    "details": {"latitude": ["유효한 좌표를 입력하세요."]}
  },
  "request_id": "00000000-0000-0000-0000-000000000000"
}
```

request_id는 서버에서 발급하며 `X-Request-ID`에도 포함한다. 클라이언트는 안정적인 code/status를 사용하고 표시 문구에 로직을 의존하지 않는다. 500에는 내부 예외·DB 정보를 노출하지 않는다. `/health`, `/ready`는 운영 probe용 `{status}` 응답이며 API envelope와 구별한다.

## Phase 2 — 인증

| 메서드·경로 | 입력 | 성공 |
|---|---|---|
| POST /api/v1/auth/register | email, password, display_name | 201: id, email, display_name, date_joined |
| POST /api/v1/auth/token | email, password | 200: access, refresh |
| POST /api/v1/auth/token/refresh | refresh | 200: 새 access, 새 refresh |
| POST /api/v1/auth/logout | refresh | 204 |
| GET /api/v1/me | Bearer access | 200: id, email, display_name, date_joined |

이메일은 정규화한다. 중복/약한 비밀번호는 400. access 5분, refresh 7일이며 갱신마다 rotation/blacklist를 적용한다. 동시 갱신은 하나만 성공한다. 만료·재사용은 401이고 다시 로그인해야 한다. 비활성 계정은 로그인·갱신·me에서 거부한다.

로그아웃은 access가 만료돼도 호출할 수 있다. refresh를 소유한 요청은 그 토큰을 폐기하는 것만 가능하다. 이미 폐기된 refresh로 직접 로그아웃하면 401이다. 웹 중계는 이미 무효인 refresh도 쿠키 제거 후 204로 처리한다. 기존 access는 만료 전까지 유효할 수 있다.

Next.js `/api/auth/*`는 웹 전용 어댑터다. 브라우저에 access/refresh JSON을 반환하지 않는다. CSRF 발급 GET 외의 인증 POST는 Origin/CSRF 검증이 필요하다. Django Admin은 세션/CSRF를 사용한다.

## Phase 3 — 공개 카탈로그

- `GET /api/v1/characters`: 활성 Character 목록.
- `GET /api/v1/characters/{uuid}`: id, code, name, description.
- `GET /api/v1/characters/{uuid}/variants`: 활성 Variant 목록. 항목은 id, character(UUID), code, name, rarity, asset_key.
- 부모 Character가 비활성이면 상세/Variant 목록은 404.
- 데이터 변경은 Admin에서 수행한다. 별도 운영 CRUD API는 없다.

## Phase 4 — Nearby

`GET /api/v1/spots/nearby`는 인증이 필요하다.

| Query | 규약 |
|---|---|
| latitude | 필수, -90~90 |
| longitude | 필수, -180~180 |
| radius_m | 기본 1000, 0 초과·최대 5000 |
| page / page_size | 공통 페이지 규약 |

NaN/Infinity, 범위 밖 좌표·반경은 보정하지 않고 400이다. 활성 Spot만 조회하며 distance_m, id 오름차순으로 정렬한다. 검색 기준 좌표가 바뀌면 페이지를 처음부터 요청한다.

각 결과는 id, code, name, description, `location: {latitude, longitude}`, interaction_radius_m, distance_m을 갖는다. 좌표는 저장하지 않는다. interaction_radius_m는 향후 상호작용 허용 거리이며 검색 반경과 다르다.

## OpenAPI와 후속

`GET /api/v1/schema`에서 schema를 제공하고 CI에서 `manage.py spectacular --validate --fail-on-warn`으로 검증한다. 공통 오류 envelope도 schema에 포함한다.

Phase 5~6의 계획 경로는 `POST /encounters`, `POST /encounters/{id}/capture`, `GET /collection`이다. 현재 구현하지 않았다. Capture 재요청은 저장된 최종 결과를 반환하며 클라이언트가 성공 여부·보상을 지정할 수 없게 한다.
