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

Phase 6은 아래 Capture·Collection 계약을 제공한다. Capture 재요청은 저장된 최종 결과를 반환하며 클라이언트가 성공 여부·보상을 지정할 수 없다.


## Phase 5 — Encounter

`POST /api/v1/encounters`는 JWT 인증이 필요하다. 요청은 `spot_id`(UUID), `latitude`(-90~90), `longitude`(-180~180)만 허용한다. NaN/Infinity·누락·정의되지 않은 필드는 400이다. 사용자·Variant·status·만료 시각은 클라이언트가 결정하지 않는다.

응답은 `id`, `spot_id`, `character_variant_id`(UUID 문자열), `spawned_at`, `expires_at`(UTC ISO 8601), `status`(active/expired/captured)의 직접 객체다. 신규 생성은 201, 같은 User·Spot의 미만료 결과 재사용은 200이다. 재사용해도 Variant와 TTL은 바뀌지 않는다.

| 실패 조건 | status / error.code | details.reason |
|---|---|---|
| 입력 오류 | 400 / validation_error | 필드별 오류 또는 non_field_errors |
| 인증 실패 | 401 / authentication_failed | 기존 인증 규약 |
| Spot 없음·비활성 | 404 / not_found | 기존 detail |
| 상호작용 반경 밖 | 403 / permission_denied | out_of_range |
| 신규 발급 가능한 Rule 없음 | 409 / conflict | no_spawn_rule |

거리는 Spot의 geography와 ST_DWithin으로 계산하고 interaction_radius_m 경계를 포함한다. Nearby의 검색 반경은 사용하지 않는다. GPS 위조나 실제 방문을 증명하는 기능은 아니다.

재요청도 인증·Spot 활성·위치를 검증한다. 이미 발급한 결과는 Rule 기간 종료·Rule/카탈로그 비활성화에도 TTL까지 유지한다. 신규 발급의 기간 검증 시각은 행 잠금 대기 이후이며, Rule 종료 시각에 맞춰 TTL을 줄이지 않는다.

`GET /api/v1/encounters/{id}`는 본인 소유만 반환한다. 타인 소유와 미존재는 404다. 조회에는 좌표가 필요 없고, 미포획 Encounter가 만료돼도 200 및 status=expired를 반환한다. captured는 시간이 지나도 유지한다. GET은 DB를 수정하지 않는다. Encounter 목록·수정·삭제 API는 제공하지 않는다. Capture 동작은 아래 Phase 6 API에서 제공한다.

POST 200/201/409 및 GET 200을 OpenAPI에 기록하고 실제 응답의 필드·타입·required를 테스트한다. request_id, no-store, 내부 오류 일반화와 민감정보 로그 차단 규약을 유지한다.


## Phase 6 — Capture

`POST /api/v1/encounters/{id}/capture`는 JWT 인증이 필요하다. 본문은 생략 또는 `{}`만 허용한다. 위치·성공 여부·보상·사용자·Variant 등 추가 필드나 잘못된 본문은 400이다. 좌표 재전송 없이 발급 시 검증과 TTL을 자격으로 사용한다.

최초 성공과 재시도 모두 200이며 응답 필드는 `id`(CaptureResult), `encounter_id`, `collection_entry_id`, `character_variant_id`, `captured_spot_id`(모두 UUID 문자열), `captured_at`(UTC ISO 8601), `status`("captured")다. 동일 Encounter의 성공 재시도는 같은 body를 반환한다. 변경 가능한 이름/Rarity는 포함하지 않는다.

- 인증/비활성 계정은 기존 401, 미존재/다른 사용자 소유/잘못된 UUID 경로는 404.
- 최초 Capture의 expires_at <= 잠금 이후 판단 시각이거나 저장 status가 expired이면 409/conflict, details.reason=encounter_expired. 실패 시 새 데이터나 만료 상태 update는 없다.
- captured 상태의 재시도는 원래 TTL 이후에도 저장 결과를 반환한다. 인증·소유권·요청 형식은 항상 검사한다.
- Spot·Rule·카탈로그의 사후 비활성화는 발급 결과를 취소하지 않는다. 최초 Capture 시에도 재검증하지 않는다.
- 저장 상태와 결과/획득 개체가 불일치하면 추가 지급 없이 일반화된 500을 반환하고 안전한 로그를 남긴다.

## Phase 6 — Collection

`GET /api/v1/collection`은 본인 획득 개체만 반환한다. 사용자 파라미터로 조회 대상을 변경할 수 없다. 기존 `{count,next,previous,results}` pagination(기본 20, 최대 100)을 사용하고, 획득 시각 내림차순·동률 id 내림차순으로 고정한다. 검색/사용자 정렬/통계/진행률은 없다. 새 획득이 페이지 사이에 추가되면 page-number의 위치가 바뀔 수 있다.

항목 필드:

- `id`, `encounter_id`: UUID 문자열.
- `character`: id, code, name.
- `character_variant`: id, code, name, rarity, asset_key.
- `captured_at`: UTC ISO 8601.
- `captured_spot`: id, code, name.

이름·등급은 현재 카탈로그 값이다. 비활성 카탈로그·Spot도 획득 이력에 남는다. 동일 Variant 반복 획득은 별도 항목으로 반환하며 GPS 좌표는 포함하지 않는다. 관계를 select_related로 조회해 페이지 항목 수에 따라 쿼리가 늘지 않게 한다.

## Phase 7 — Community

공개 Post/Comment GET은 비로그인에도 허용한다. 변경은 기존 Bearer JWT가 필요하다. 공개 author는 `{id, display_name}`만 반환한다. 숨김/삭제 데이터는 공개 조회·수정에서 404, 공개 콘텐츠의 타인 수정/삭제는 403이다. 작성자의 숨김 콘텐츠 삭제와 반복 삭제는 204다.

| 메서드·경로 (앞에 /api/v1) | 입력 | 성공 |
|---|---|---|
| GET /community/posts | category, page, page_size | 200 pagination |
| POST /community/posts | category, title, content | 201 상세 |
| GET /community/posts/{id} | — | 200 상세 |
| PATCH /community/posts/{id} | category/title/content 부분 수정 | 200 상세 |
| DELETE /community/posts/{id} | — | 204 |
| GET /community/posts/{id}/comments | page, page_size | 200 pagination |
| POST /community/posts/{id}/comments | content | 201 댓글 |
| PATCH /community/comments/{id} | content | 200 댓글 |
| DELETE /community/comments/{id} | — | 204 |
| PUT /community/posts/{id}/like | 생략 또는 {} | 204, 반복 포함 |
| DELETE /community/posts/{id}/like | 생략 또는 {} | 204, 반복 포함 |
| POST /community/reports | target_type, target_id, reason, details(선택) | 201 최초 / 200 기존 접수 |

JSON 입력만 지원하며, 작성·수정·Like·Report의 정의되지 않은 필드는 400이다. 제목 200자, 게시글 본문 10000자, 댓글 2000자, 신고 설명 1000자이며 공백만 있는 콘텐츠는 거부한다. category는 free/goods/collection/spot/guide/event/trade. 잘못된 category 필터는 400이다.

Post 목록 필드는 id, author, category, title, created_at, updated_at, like_count, comment_count, is_liked이며 상세에 content를 추가한다. Comment는 id, post_id, author, content, created_at, updated_at. 목록은 기존 pagination(20/100), Post는 created_at/id 내림차순, Comment는 오름차순이다. comment_count는 공개 댓글만 포함한다. 비로그인의 is_liked는 false다. 검색·사용자 정렬은 제공하지 않는다.

Like PUT은 공개 Post에만 허용하며 DELETE는 숨김/삭제 Post에도 본인 Like 제거를 허용한다. 혼합 PUT/DELETE 동시 요청은 DB 직렬화 순서대로 최종 상태가 결정된다.

Report target_type은 post/comment, target_id는 UUID, reason은 spam/abuse/inappropriate/other다. 신규 신고는 공개 대상만 허용한다. 자기 신고는 400/validation_error와 details.reason=self_report다. 중복은 원래 신고를 반환하며 사유를 덮어쓰거나 재개하지 않는다. 이미 접수됐다면 대상 숨김/삭제 이후에도 중복 결과를 반환한다. 응답은 id, target_type, target_id, status, created_at이며 증거·자유 입력 설명은 반환하지 않는다.

Admin moderation은 별도의 세션/CSRF 화면이다. hidden/deleted 차이와 신고 처리 정책은 domain.md를 따른다. 별도 공개 moderation API나 사용자 신고 조회 API는 없다.


## Phase 8 — 공개 News

GET /api/v1/news, GET /api/v1/news/{id}: 인증 없이 발행된 News만 조회한다. 필드는 id/title/category/summary/source({code,name})/source_url/published_at/created_at이다. published_at은 원문 발표 UTC, created_at은 승인·서비스 발행 시각이다. 첫 Source의 summary는 빈 문자열이다. category는 news/goods/event/collaboration이고 잘못된 필터는 400이다. 기본 20/최대 100 pagination, published_at DESC/id DESC를 사용한다. Source 비활성화는 이미 발행된 News를 숨기지 않는다. 쓰기 API, source 필터, 검색, 사용자 정렬은 없다. 검수는 Admin의 CSRF 보호 POST와 별도 review_newscandidate 권한으로만 수행한다.

## Phase 10 — 운영 Batch API

`/api/v1/batch` 아래 API는 활성 staff와 `batch.view_batch`를 요구한다. 미인증 401, 권한 부족 403. 응답은 no-store다. 변경은 추가 `run_batch` 또는 `manage_batch` 권한을 요구하며 실패 확정에는 둘 다 필요하다. Django Admin은 조회 전용이다.

| 경로 | 메서드 / 기능 |
|---|---|
| /capabilities | GET: view/run/manage |
| /jobs | GET: 허용된 두 Job, 실행 정책·마지막/현재 실행 |
| /jobs/{id} | PATCH: enabled, source_id만 |
| /sources | GET: 선택 가능한 Source 정보 |
| /schedules | GET, POST: Job당 일정 하나 |
| /schedules/{id} | GET, PATCH: Cron·시간대·기간·활성 상태 |
| /jobs/{id}/runs | POST: 신규 202, 동일 접수 200 |
| /executions | GET: job/status 필터, 20/100 pagination, requested_at DESC/id DESC |
| /executions/{id} | GET: 시도별 결과·안전한 실패·task/worker·Retry 관계 |
| /executions/{id}/retry | POST: 실패 원본에서 새 접수 202, 이미 있는 후속 200 |
| /executions/{id}/confirm-failure | POST: worker_stopped=true 명시 확인, stale만 200 |

Run Now/Retry에는 UUID `Idempotency-Key`와 빈 JSON 객체를 사용한다. 같은 actor/job/key로 다른 동작을 요청하면 409. 다른 키로 미완료 Job을 요청해도 409(job_busy). 202는 DB 원장 접수이며 broker 전송/수집 성공이 아니다. 네트워크 응답 유실 후 클라이언트는 같은 키를 유지한다. 일반 공개 API와 수집/검수 정책은 변하지 않는다.
