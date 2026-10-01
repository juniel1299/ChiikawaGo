# 도메인 경계

## 소유권

| 모듈 | 소유 데이터·규칙 | 상태 |
|---|---|---|
| accounts | 사용자, 이메일 식별, 인증, 활성 상태, 권한 | Phase 1 스키마 / Phase 2 기능 |
| characters | Character, Variant, Rarity, Asset 참조 | Phase 3 |
| spatial | Spot, 좌표, 공간 조회, 거리 계산 | Phase 4 |
| encounters | Spawn Rule, 발급·만료, Capture 검증·결과 | 후속 Phase 5~6 |
| collection | 사용자별 획득 개체, 도감·진행률 조회 | 후속 Phase 6 |
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

## 후속 Capture 트랜잭션

Capture 서비스가 `transaction.atomic()` 안에서 Encounter 행을 잠그고 소유자·만료·위치·상태를 검증한다. 최종 결과와 성공 시 Collection 생성을 같은 트랜잭션으로 커밋한다. Encounter별 결과와 결과별 획득 개체에 유일 제약을 둔다. 완료된 요청은 기존 결과를 반환한다. Redis lock이나 메시지 큐가 이 일관성의 전제 조건이 되어서는 안 된다.

이 설계는 방향만 확정했다. 출현 확률·포획 성공률·이벤트 조건은 Phase 5 설계에서 확정하며 현재 테이블·빈 app은 만들지 않는다.
