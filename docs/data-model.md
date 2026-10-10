# 데이터 모델

## 공통 규칙 — 초기 기본값

도메인 모델은 UUID PK, UTC timestamp, 명시적인 FK를 쓴다. UUID는 권한 검증을 대신하지 않는다. 핵심 관계를 JSON에 숨기거나 모든 테이블에 soft delete를 넣지 않는다. 상태 관리는 필요한 모델의 `is_active`로 처리한다.

## 현재 모델

| 모델 | 주요 필드 | 제약·인덱스 |
|---|---|---|
| User | id, email, password, display_name, is_active, is_staff, date_joined | email unique + Lower(email) unique |
| Character | id, code, name, description, is_active, created_at, updated_at | code unique |
| CharacterVariant | id, character FK, code, name, rarity, asset_key, is_active, timestamps | (character, code) unique, rarity check |
| Spot | id, code, name, description, location, interaction_radius_m, is_active, timestamps | code unique, radius > 0 check, location GiST |

### Account

`AbstractUser`에서 username을 제거하고 이메일을 로그인 식별자로 쓴다. 기본 권한·그룹·날짜 등 Django 필드는 유지한다. Manager/저장 시 이메일 전체를 소문자로 정규화하고 DB의 함수 유일 제약으로 우회/동시 삽입도 방어한다. Profile 테이블 없이 display_name부터 시작한다. 비밀번호는 Django 해시만 저장한다.

### Character와 Variant

기본형도 Variant 하나로 표현한다. 등급은 `common`, `rare`, `epic` TextChoices이며 DB check도 둔다. 등급이 출현/포획 확률을 자동 결정하지 않는다. asset_key는 선택적인 Object Storage 키 참조이며 Blob이나 실제 Asset 업로드는 없다.

Variant의 Character FK는 PROTECT다. 카탈로그를 삭제해 이력 의미가 사라지지 않도록 비활성화를 우선한다. 향후 획득 개체가 Variant/Spot을 참조할 때도 보호 관계를 추가한다. 자유로운 등급 편집이나 여러 해상도·애니메이션이 필요하면 Rarity/Asset 테이블을 추가할 수 있다.

### Spatial

`PointField(srid=4326, geography=True, spatial_index=True)`를 사용한다. 내부 Point는 **경도, 위도** 순서다. API/Admin은 이름이 있는 latitude/longitude 입력을 사용한다. Admin은 숫자 입력으로 구현해 지도 서비스 의존성을 추가하지 않았다.

`ST_DWithin`으로 활성 Spot을 반경 필터링한 뒤 `ST_Distance`로 거리를 산출한다. geography의 미터 단위를 사용한다. geometry는 특정 투영좌표계나 더 복잡한 공간 연산이 필요할 때 검토한다. `interaction_radius_m` 기본값 100m는 이후 상호작용 검증용이며 Nearby 검색 반경과 별개다.

사용자 현재 위치는 저장하지 않는다. 원시 SQL로 PostGIS에 잘못된 좌표를 쓰면 정규화될 수 있으므로 초기 관리 경로의 좌표 검증을 유지한다. 운영 데이터 입력 경로가 추가되면 같은 검증을 적용한다.

## Migration과 운영 데이터

Custom User는 첫 accounts migration에 들어간다. spatial 첫 migration은 `CreateExtension('postgis')`, 다음 migration은 Spot이다. 빈 PostgreSQL에 적용할 때 extension 생성 권한이 필요하며 운영에서는 DBA/프로비저닝 단계에서 미리 설치할 수 있다.

샘플 데이터는 명시적인 `seed_demo` 명령으로 등록한다. startup이나 migration에 캐릭터·계정 데이터를 숨기지 않는다. 기본 관리자 비밀번호나 고정 계정은 생성하지 않는다.

## Phase 5~6 구현 관계

```text
User ──< Encounter >── Spot
              └────── CharacterVariant >── Character
Encounter ── 0..1 CaptureResult ── 0..1 CollectionEntry >── User
```

Encounter는 소유자·Spot·Variant·발급/만료 시각·상태를 갖는다. Encounter당 하나의 최종 결과, 성공 결과당 하나의 CollectionEntry를 DB 유일 제약으로 보장한다. 동일 Variant의 다회 획득은 허용한다. 진행률은 아직 구현하지 않는다.

CaptureResult·CollectionEntry는 Phase 6에 구현했다. 이벤트와 위치 증빙 저장 정책은 후속 요구사항이다. Redis TTL이나 distributed lock 없이 DB transaction과 행 잠금으로 일관성을 유지한다.


## Phase 5 모델

| 모델 | 필드 | 제약 |
|---|---|---|
| SpawnRule | UUID id, spot FK, character_variant FK, weight(default 1), is_active, nullable starts_at/ends_at, created_at/updated_at | weight > 0, 두 시각이 있으면 starts_at < ends_at, (spot, character_variant) unique |
| Encounter | UUID id, user/spot/character_variant FK, spawned_at, expires_at, status | expires_at > spawned_at, status는 active/expired/captured, status=active에 한해 (user, spot) unique |

FK는 모두 PROTECT다. 사용자 탈퇴·익명화는 별도 정책으로 정한다. migration은 두 모델의 테이블·제약 추가만 수행하고 운영 데이터를 삽입하지 않는다.

Rule은 Spot·Variant 조합당 하나의 기간만 가진다. 반복 시간대·요일·날씨·이벤트 조건은 없다. 시작은 포함하고 종료는 제외한다. null은 해당 방향의 기간 제한이 없음을 뜻한다. Rule·Variant·부모 Character가 모두 활성일 때 신규 후보가 된다. 양의 정수 weight의 합을 100으로 제한하지 않으며, 정수 난수와 누적 구간으로 한 개를 선택한다. 별도의 미출현 확률은 없다.

TTL은 서버 설정 ENCOUNTER_TTL_SECONDS=180이다. expires_at <= 현재 시각이면 실효 상태는 expired다. GET/Admin은 DB를 변경하지 않고 실효 상태를 표시한다. 같은 User·Spot의 새 발급 시에만 만료된 active 행을 expired로 갱신하고 새 행을 같은 트랜잭션에서 삽입한다. 오류 발생 시 둘 다 롤백한다. 따라서 DB의 active는 아직 정리되지 않은 만료 행을 포함할 수 있으며, 이용 가능 판단은 반드시 expires_at도 확인한다.

현재 시각을 조건부 unique 제약에 넣지 않는다. Batch/Redis는 필요 없다. captured 상태와 결과·수집 관계는 아래 Phase 6 모델을 따른다. 발급된 Variant FK와 유효기간을 보존하며 Rule FK·확률 스냅샷·사용자 좌표는 저장하지 않는다.


## Phase 6 모델

| 모델 | 필드 | 제약/참조 |
|---|---|---|
| CaptureResult | UUID id, encounter OneToOne, captured_at | Encounter별 최대 한 결과, PROTECT |
| CollectionEntry | UUID id, user FK, character_variant FK, capture_result OneToOne | 결과별 최대 한 획득 개체, 모든 FK PROTECT |

CaptureResult는 성공한 최종 결과만 기록한다. 확률적 실패·만료 오류 기록은 만들지 않는다. Collection의 (user, character_variant)는 unique가 아니다. 생성 함수는 잠긴 Encounter의 사용자/Variant로만 획득 개체를 만든다. 일반 FK는 교차 테이블 사용자/Variant 값 일치까지 강제하지 않으며 서비스와 테스트로 보장한다.

획득 시각은 CaptureResult.captured_at, Encounter는 CaptureResult.encounter, 획득 Spot은 그 Encounter.spot을 조회한다. 별도 시각/Spot/이름 스냅샷은 없다. 이름·Rarity·Spot 이름은 현재 값이므로 운영자가 변경하면 기존 Collection 표시에도 반영된다. 비활성화돼도 획득 이력을 숨기지 않는다.

captured는 최종 상태다. effective_status는 active만 만료로 계산하므로 시간이 지나도 captured를 유지한다. 만료 Capture 거부 시 DB status를 갱신하지 않는다. active 조건부 unique 제약은 유지되므로 Capture 후 새 발급이 가능하다.

encounters의 0002 migration은 기존 상태 제약에 captured를 추가하고 CaptureResult를 만든다. collection의 0001 migration은 CollectionEntry를 만든다. Phase 5의 이미 적용한 0001은 변경하지 않으며, 기존 Encounter 자동 포획·획득 데이터 생성은 없다. 빈 DB와 Phase 5 → Phase 6 업그레이드를 모두 검증한다.

## Phase 7 — Community

| 모델 | 필드 | 제약·조회 인덱스 |
|---|---|---|
| Post | UUID, author(PROTECT), category, title(200), content(10000), status, deleted_at, created_at, updated_at | category/status check, 삭제 시각·본문 제거 check, 공개 최신순 및 category/최신순 부분 인덱스 |
| Comment | UUID, post(PROTECT), author(PROTECT), content(2000), status, deleted_at, timestamps | status/삭제 check, 공개 post/created_at/id 부분 인덱스 |
| Like | UUID, user(PROTECT), post(CASCADE), created_at | user/post unique |
| Report | UUID, reporter(PROTECT), nullable post/comment(PROTECT), reason, details(1000), status, snapshot_title/content, created_at, reviewed_at/by(PROTECT) | 대상 XOR, reporter/post 및 reporter/comment 조건부 unique, reason/status/처리 메타데이터·증거 제거 check |

Post.Category는 free/goods/collection/spot/guide/event/trade다. content는 일반 텍스트이며 첨부/Blob/Base64 이미지 저장 필드는 없다. 상태는 visible/hidden/deleted. 삭제는 원문과 Like를 제거하는 제한적 soft delete이며 작성자 FK와 대상 ID를 보존한다. 계정 탈퇴/익명화는 별도 요구사항이다. count 컬럼은 없고 목록에서 집계한다.

Report.reason은 spam/abuse/inappropriate/other, status는 pending/resolved/dismissed다. 최초 신고 시 잠근 대상 원문을 snapshot으로 저장한다. 댓글 신고에는 댓글 본문만 복사한다. 대상 수정·삭제 후에도 pending 증거는 유지한다. 완료 시 snapshot과 자유 입력 details를 비우고 reviewer/time을 기록한다. 처리된 신고는 재개하지 않는다. 대상별 사용자 중복 신고는 기존 접수 결과를 반환한다.

미처리 신고의 기한 기반 자동 제거, 대댓글, Category 관리, 첨부 Object Storage, Spot/Variant/Event 연결은 Future Consideration이며 이번 migration에 포함하지 않는다.


## Phase 8 — News

Source는 UUID/code/name/source_type/adapter_key/base_url/is_active/policy_url/policy_checked_at/policy_notes/next_request_at/timestamps를 가진다. adapter는 unique로 동일 출처를 중복 등록하지 못하게 하며 URL은 DreamNews 드리텍으로 제한하고 Source는 명시적으로 Admin에서 등록한다. 자동 운영 데이터 migration은 없다. next_request_at은 동시 수동 요청 사이 간격을 공유하는 시각이며 스케줄이 아니다.

RawItem은 Source, external_id(앞자리 0 보존), canonical_url, title, published_at, collected_at, metadata_hash를 저장한다. 전체 HTML/본문/이미지를 보관하지 않는다. Source+external_id 및 Source+canonical_url은 각각 unique이며 제목/hash는 unique가 아니다.

NewsCandidate는 RawItem OneToOne과 title/category/summary/status/reviewed_by/reviewed_at을 가진다. pending/published/rejected와 검수 정보의 일치에 DB check를 둔다. News는 Candidate OneToOne, Source, source_url/title/category/summary/published_at/created_at을 가진다. FK는 PROTECT이며 News는 승인 당시 값의 snapshot이다. summary는 첫 adapter에서 빈 문자열, category는 goods다. cross-table snapshot 일치는 서비스와 테스트가 보장한다. News의 최신순 및 category 최신순 인덱스를 둔다.

## Phase 10 — Batch 모델

- BatchJob: UUID, 허용 code(unique/check), name/description, enabled, nullable Source(PROTECT), timestamps. 초기 등록 명령만 두 비활성 Job을 만들고 migration은 데이터를 넣지 않는다. timeout/retry 정책은 코드 registry에 있으며 화면에서 읽기 전용이다.
- BatchSchedule: Job OneToOne(PROTECT), 숫자 기반 5필드 Cron, timezone(UTC/Asia/Seoul check), enabled, starts_at/ends_at, last_scheduled_at/next_run_at. 시작 포함·종료 제외, UTC 저장. Cron 계산은 croniter 6.2.4, 날짜 탐색은 8년으로 제한한다. 일/요일 동시 제한은 OR다.
- BatchExecution: Job/Schedule/retry_of/요청자(PROTECT), 예정·접수·시작·현재 시도·종료 시각, 접수 UUID 키, 제한된 Source/실행 정책 snapshot, status/attempt, 전달 예약·발행 횟수·task ID, worker, 시도별 안전한 결과, 실패·운영 확인 정보. 별도 Attempt/result-backend 테이블은 없다.
- Job별 미완료 행 조건부 unique, schedule+scheduled_for unique, actor+job+key 조건부 unique(NULL actor도 중복 방지), retry_of OneToOne, status/trigger/attempt/종료 시각 check로 보호한다. 결과는 queued → running → success/failed 또는 retry_wait → running이다.
- 자동 retry는 같은 원장에서 최대 세 시도, 운영자 Retry는 새 행이며 실패한 원본당 후속 하나다. 동기 실행은 task ID가 없고 scheduler 재발행 대상에서 제외된다.

next_dispatch_at은 짧은 잠금으로 발행 선점과 유실 복구를 지원한다. publisher confirm 후 Worker 시작이 없으면 120초 뒤 재확인하고 발행 실패는 30초 뒤 재시도한다. commit/publish 원자성이나 exactly-once 부작용을 보장하지 않는다. stale은 현재 시도 시작+hard limit+120초로 계산하며 저장 상태를 자동 변경하지 않는다.
