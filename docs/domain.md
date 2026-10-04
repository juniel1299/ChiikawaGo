# 도메인 경계

## 소유권

| 모듈 | 소유 데이터·규칙 | 상태 |
|---|---|---|
| accounts | 사용자, 이메일 식별, 인증, 활성 상태, 권한 | Phase 1 스키마 / Phase 2 기능 |
| characters | Character, Variant, Rarity, Asset 참조 | Phase 3 |
| spatial | Spot, 좌표, 공간 조회, 거리 계산 | Phase 4 |
| encounters | Spawn Rule, 발급·만료·재사용, Capture 최종 결과 | Phase 5~6 |
| collection | 사용자별 획득 개체와 본인 목록 | Phase 6; 진행률은 후속 |
| community | 게시글·댓글·반응·신고 | 후속 |
| news | 수집 출처·후보·검수·발행 | 후속 |
| batch | Job·Schedule·Execution, 실행 운영 | 후속 |
| events / notifications | 이벤트 조건 / 알림 전달 | 후속 |

## 주요 결정

**Capture는 encounters의 유스케이스다.** Encounter를 확인하고 소비하는 과정과 강한 트랜잭션 관계가 있다. 별도 app보다 검증과 상태 변경을 한 흐름에서 읽기 쉽다. 규칙·운영 특성이 독립적으로 커질 때 분리할 수 있다.

**Spawn Rule은 encounters가 소유한다.** spatial은 위치 사실과 거리 계산을 담당하고 출현 시간·확률·캐릭터 선택은 게임 규칙이다. 이는 PROMPT의 Spatial 기능 분류를 구현 책임 관점으로 구체화한 결정이다. 단순한 위치별 조건만 있다면 spatial에 둘 수도 있지만 출현 규칙의 확장 방향을 고려해 분리한다.

**캐릭터 정의와 보유 개체는 다르다.** characters는 카탈로그, collection은 획득 이력을 소유한다. 동일 Variant를 여러 번 수집하는 것과 동일 Capture를 중복 반영하는 것을 구별한다.

## Django에서 경계를 지키는 방법

- 하나의 DB에서 FK와 ORM 관계를 허용한다. 독립 DB나 네트워크 호출을 흉내 내지 않는다.
- 타 도메인 변경은 해당 도메인의 서비스 함수를 통해 수행한다. 단순 조회는 ORM, 복잡하거나 반복되는 조회는 selector로 표현한다.
- Serializer는 입력/출력, View는 HTTP·권한, Model은 스키마·제약을 담당한다.
- 다중 모델 변경과 비즈니스 트랜잭션이 생길 때 service를 추가한다. 단순 CRUD마다 계층을 만들지 않는다.
- 핵심 상태 변경을 signal에 숨기지 않는다.
- 범용 Repository/Interface/Factory 또는 DDD 기반 클래스는 없다. Django ORM으로 부족한 문제가 생길 때만 추상화한다.

## Capture 트랜잭션

Capture 서비스가 `transaction.atomic()` 안에서 Encounter 행을 잠그고 소유자·만료·상태를 검증한다. Capture 위치 재검증은 하지 않는다. 최종 결과와 성공 시 Collection 생성을 같은 트랜잭션으로 커밋한다. Encounter별 결과와 결과별 획득 개체에 유일 제약을 둔다. 완료된 요청은 기존 결과를 반환한다. Redis lock이나 메시지 큐가 이 일관성의 전제 조건이 되어서는 안 된다.

Phase 6는 유효한 Encounter라면 항상 성공한다. CaptureResult와 CollectionEntry를 구현하며 포획 확률·아이템·이벤트 조건은 추가하지 않는다.


## Phase 5 발급 책임과 일관성

SpawnRule과 Encounter는 encounters가 소유한다. 공간 접근 허용 판단은 spatial의 geography 조회를 재사용한다. 생성 service가 하나의 transaction.atomic 안에서 Spot → 기존 active Encounter → SpawnRule(UUID 순서)를 잠근다. 향후 여러 모델을 잠그는 변경도 이 순서를 거슬러 잠그지 않는다.

Spot은 NO KEY UPDATE로 잠근다. 아직 Encounter가 없는 첫 요청도 직렬화되며, FK 참조 삽입을 불필요하게 막지 않는다. 같은 Spot의 서로 다른 사용자도 짧게 순차 처리된다. 다른 Spot은 병렬 진행할 수 있다. 전용 User·Spot 잠금 테이블은 경합이 측정되기 전에는 추가하지 않는다.

Rule 변경이 먼저 커밋되면 신규 발급에 반영한다. 생성이 Rule 잠금을 먼저 획득하면 해당 발급을 완료한 뒤 관리자 변경이 진행된다. 잠금 대기 이후의 시각으로 Rule 기간을 판단한다. 카탈로그 활성 여부는 후보 조회 시점의 값이며, 이후 변경은 발급 결과를 소급 취소하지 않는다. Rule 조회 후 추가된 Rule은 다음 발급부터 반영해도 된다.

미만료 Encounter는 동일 ID·Variant·만료 시각으로 재사용한다. 재요청에서도 인증·Spot 활성·현재 거리를 검증한다. Rule/카탈로그 비활성화나 Rule 기간 종료는 기존 발급을 취소하지 않는다. 이는 TTL 내 재사용이며 영구적인 idempotency가 아니다. 위치 입력은 저장·로그 기록하지 않는다.


## Phase 6 Capture와 Collection

Capture는 Encounter만 NO KEY UPDATE로 잠근다. 이후 Spot이나 Rule을 잠그지 않아 Phase 5의 Spot → Encounter 잠금 순서와 역전되지 않는다. 같은 Encounter 요청은 잠금으로 직렬화하고, 다른 Encounter의 Capture는 같은 Spot이어도 독립적으로 처리한다.

인증·소유권은 매번 검증한다. captured 상태이면 일관된 기존 CaptureResult/CollectionEntry를 만료보다 먼저 확인해 반환한다. 최초 처리만 잠금 획득 후 시각으로 실효 상태를 검사한다. 성공 결과 → collection 서비스의 획득 개체 생성 → Encounter captured 변경을 하나의 atomic 안에서 수행한다. 실패는 모두 롤백한다. 별도 retry·signal·메시지 큐는 없다.

collection 서비스는 CaptureResult의 Encounter에서 사용자와 Variant를 결정한다. 클라이언트는 소유자·결과·보상을 지정할 수 없다. DB는 OneToOne 관계의 중복을 막고, 상태와 두 행의 일치는 트랜잭션으로 보장한다. 상태/결과/획득 개체 불일치를 발견하면 자동 복구나 지급 없이 일반화된 500과 안전한 예외 로그로 처리한다.

위치는 발급 시에만 검증한다. 발급 후 Spot/Rule/카탈로그 비활성화도 TTL 내 Capture를 취소하지 않는다. Capture 성공 후 같은 Spot에서 새 Encounter와 동일 Variant 재획득을 허용하며, 쿨다운·Rate Limit은 이번 단계에 없다. 성공한 결과의 재요청은 원래 TTL 이후에도 동일 결과를 반환한다.
