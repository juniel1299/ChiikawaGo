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

## Phase 5~6 관계 초안 — 미구현

```text
User ──< Encounter >── Spot
              └────── CharacterVariant >── Character
Encounter ── 0..1 CaptureResult ── 0..1 CollectionEntry >── User
```

Encounter는 소유자·Spot·Variant·발급/만료 시각·상태를 갖는다. Encounter당 하나의 최종 결과, 성공 결과당 하나의 CollectionEntry를 DB 유일 제약으로 보장한다. 동일 Variant의 다회 획득은 허용한다. 진행률은 초기 집계 조회로 산출한다.

Spawn Rule 상세, 확률, 이벤트 조건, 위치 증빙 저장 정책은 Phase 5에서 결정한다. Redis TTL이나 distributed lock 없이도 DB transaction과 행 잠금으로 일관성을 유지한다.
