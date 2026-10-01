# CHII WORLD Project Master Prompt

## 1. 프로젝트 목적

이 프로젝트는 치이카와를 테마로 한 위치 기반 수집형 웹/앱 서비스다.

단순 CRUD 토이 프로젝트가 아니라 실제 서비스 회사에서 사용하는 개발 방식, 아키텍처, 운영 구조를 학습하고 경험하는 것을 가장 중요한 목표로 한다.

개발자는 현재 실무에서 주로 다음 기술을 사용하고 있다.

- Spring Boot
- Java
- React
- JavaScript
- Oracle
- MyBatis

따라서 이 프로젝트에서는 기존 실무 기술을 반복해서 사용하기보다는, 사용 경험이 적거나 없는 새로운 기술을 적극적으로 사용한다.

---

# 2. 서비스 컨셉

Pokemon GO와 유사한 위치 기반 수집 시스템을 기본 컨셉으로 한다.

사용자는 실제 위치를 기반으로 주변 Spot을 탐색할 수 있다.

특정 Spot 근처에 접근하면 다음과 같은 행동이 가능하다.

- 캐릭터 Encounter
- 캐릭터 Capture
- 아이템 획득
- 스탬프 획득
- 배지 획득
- 이벤트 참여
- 지역 한정 보상 획득

캐릭터에는 다음과 같은 속성이 존재할 수 있다.

- 캐릭터 종류
- Variant
- Rarity
- Spawn 지역
- Spawn 시간
- Spawn 확률
- 이벤트 한정 여부

향후에는 다음 기능도 고려한다.

- 3D 캐릭터
- AR Capture
- 날씨 기반 Spawn
- 시간 기반 Spawn
- 이벤트 Spawn
- 지역 한정 캐릭터
- 사용자 간 캐릭터/아이템 교환

---

# 3. 주요 서비스 영역

프로젝트는 다음 주요 도메인으로 구성한다.

## Account

- 회원가입
- 로그인
- OAuth
- 사용자 Profile
- 권한
- 차단
- 탈퇴

## Character

- 캐릭터
- 캐릭터 Variant
- Rarity
- 캐릭터 Asset
- 캐릭터 Metadata

## Spatial

위치 기반 기능을 담당한다.

- Spot
- 사용자 위치
- Nearby Spot
- Spawn Rule
- 위치 검증
- 거리 계산
- 위치 기반 Event

PostGIS를 적극 활용한다.

향후 H3 기반 Cell 구조도 고려한다.

## Encounter

사용자가 특정 위치에서 캐릭터를 발견하는 기능.

예:

사용자 GPS
→ Nearby Spot 조회
→ Spawn Rule 확인
→ Encounter 생성
→ Encounter TTL
→ Capture 가능 상태

## Capture

캐릭터 포획 처리.

서버에서 다음을 검증한다.

- Encounter 존재 여부
- Encounter 만료 여부
- 사용자 소유 여부
- Capture 중복 여부
- 위치 조건
- Event 조건

Capture 결과는 클라이언트가 결정하지 않는다.

최종 결과는 반드시 서버에서 검증한다.

## Collection

- 사용자가 보유한 캐릭터
- Variant
- 획득 장소
- 획득 시간
- Rarity
- Collection Progress

## Community

카테고리 예:

- 자유
- 굿즈
- 캐릭터 자랑
- Spot 제보
- 공략
- 이벤트
- 교환

기능:

- 게시글
- 댓글
- 좋아요
- 조회수
- 신고
- 이미지
- 인기 게시글

## News

치이카와 관련 최신 정보를 수집한다.

수집 후보:

- 공식 사이트
- 공식 공지
- 이벤트 페이지
- 콜라보 페이지
- 굿즈 관련 페이지

데이터 수집은 Web Crawling / Web Scraping 방식으로 처리할 수 있다.

단, 크롤링 대상 사이트의 이용약관 및 robots 정책을 고려할 수 있도록 구조를 설계한다.

수집된 데이터는 바로 서비스에 노출하지 않아도 된다.

다음 Workflow를 고려한다.

Crawler
→ Raw Data
→ Normalize
→ Duplicate Check
→ Candidate
→ Admin Review
→ Publish

## Notification

다음 이벤트를 기반으로 알림을 지원한다.

- 이벤트 시작
- 특정 캐릭터 Spawn
- 근처 Event Spot
- 커뮤니티 반응
- 시스템 공지

모바일 Push는 Firebase Cloud Messaging을 고려한다.

---

# 4. 기술 스택

이번 프로젝트는 기존 실무 스택을 최대한 피한다.

## Web Frontend

- Next.js
- TypeScript
- TanStack Query
- Zustand

Next.js를 단순 SPA처럼 사용하지 않는다.

다음 기능을 적극적으로 학습한다.

- Server Component
- Client Component
- SSR
- ISR
- Route Handler
- Middleware
- Metadata
- Server Action

Web의 주요 역할:

- Community
- News
- Collection
- Profile
- Event
- Admin

---

# 5. Mobile

모바일 클라이언트는 Flutter를 사용한다.

주요 기능:

- GPS
- Map
- Nearby Spot
- Encounter
- Capture
- Collection
- Push Notification
- Camera

향후 3D 또는 AR이 필요한 경우 Unity 연동을 고려한다.

Flutter는 일반 앱 기능을 담당하고, Unity는 필요할 경우 다음 영역만 담당하도록 한다.

- 3D
- Capture Scene
- Animation
- AR

초기 버전에서는 3D/AR을 우선 구현하지 않는다.

개발 단계:

1. 2D
2. 2.5D
3. 3D
4. AR

순서로 발전시킨다.

---

# 6. Backend

Backend는 다음 기술을 사용한다.

- Python
- Django
- Django REST Framework

Spring Boot 방식의 단순한 Controller / Service / Repository 구조를 그대로 복제하지 않는다.

Django 생태계에 맞는 구조를 사용하되 비즈니스 로직이 View나 Model에 과도하게 몰리지 않도록 한다.

예상 구조:

backend/

config/

apps/

- accounts
- characters
- collection
- spatial
- encounter
- community
- news
- notifications
- events
- batch
- admin

각 도메인은 필요에 따라 다음과 같이 구성한다.

- models
- services
- selectors
- repositories
- serializers
- views
- tasks
- tests

과도한 패턴 적용은 피한다.

복잡도가 필요한 곳에만 abstraction을 추가한다.

---

# 7. Database

메인 데이터베이스:

PostgreSQL

위치 데이터:

PostGIS

적극적으로 다음 기능을 사용한다.

- Spatial Index
- Geography / Geometry
- Distance Query
- ST_DWithin
- ST_Distance

예:

Spot 테이블의 위치 데이터는 단순 latitude / longitude 컬럼만 사용하는 것보다 PostGIS Point 사용을 우선 고려한다.

향후 서비스 규모가 커질 경우:

PostGIS
→ H3
→ Cell 기반 Cache

구조도 고려한다.

---

# 8. Redis

Redis를 단순히 사용했다는 목적만으로 추가하지 않는다.

명확한 목적이 있는 곳에 사용한다.

사용 후보:

## Nearby Spot Cache

지역 Cell 단위로 Nearby Spot 정보를 Cache.

## Encounter

Encounter TTL 관리.

예:

encounter:{id}

TTL = 180 seconds

## Rate Limiting

Capture, Login, Posting 등의 API 요청 제한.

## Ranking

Redis Sorted Set을 이용한 인기 게시글 / Ranking.

## Distributed Lock

필요할 경우 중복 Capture 또는 동시에 처리될 가능성이 있는 영역에 활용.

---

# 9. 비동기 처리

Django 비동기 작업에는 Celery를 사용한다.

Message Broker는 RabbitMQ를 사용한다.

구조:

Django
→ RabbitMQ
→ Celery Worker

Celery 사용 영역:

- News Crawling
- Image Processing
- Notification
- Statistics
- Ranking
- Background Job
- Batch

향후 필요할 경우 Kafka 학습을 위한 이벤트 스트리밍 구조를 별도 실험할 수 있지만 초기 프로젝트에는 Kafka를 추가하지 않는다.

---

# 10. Batch System

이 프로젝트에서 Batch는 매우 중요한 학습 영역이다.

Batch Schedule을 Python Source Code에 직접 하드코딩하는 방식을 사용하지 않는다.

예:

Celery Beat 코드 안에 Cron을 고정해서 운영하지 않는다.

운영 Batch Schedule은 데이터베이스에서 관리한다.

Admin UI를 통해 Batch를 관리한다.

전체 구조:

Admin Web
→ Batch Management API
→ Batch Job Definition
→ Batch Schedule
→ Scheduler
→ RabbitMQ
→ Celery Worker

---

# 11. Batch Management Console

별도의 Batch 관리 화면을 개발한다.

관리자는 다음 기능을 사용할 수 있어야 한다.

## Job Management

- Job 등록
- Job 수정
- Job 활성화
- Job 비활성화
- Job 삭제

## Schedule

- Cron 설정
- 실행 시간 설정
- Timezone
- 시작일
- 종료일
- 활성 여부

## Manual Execution

관리자가 원하는 시점에 즉시 실행 가능.

예:

Run Now

## Parameter

Batch 실행 시 parameter 전달 가능.

예:

{
  "source": "official",
  "limit": 100
}

## Execution History

다음 데이터를 저장한다.

- Job
- Trigger Type
- Start Time
- End Time
- Status
- Duration
- Worker
- Retry Count
- Result
- Error

## Retry

실패한 Job을 다시 실행할 수 있다.

## Monitoring

관리화면에서 다음 정보를 확인한다.

- RUNNING
- SUCCESS
- FAILED
- WAITING

그리고:

- 처리 건수
- 성공 건수
- Skip 건수
- 실패 건수
- 실행 시간

---

# 12. Batch DB Model

기본적으로 다음 개념을 가진다.

## BatchJob

예:

- id
- code
- name
- job_type
- description
- handler
- enabled
- timeout_seconds
- max_retry_count

## BatchSchedule

- id
- job_id
- schedule_type
- cron_expression
- timezone
- start_at
- end_at
- enabled
- last_run_at
- next_run_at

## BatchExecution

- id
- job_id
- trigger_type
- started_at
- finished_at
- status
- retry_count
- worker_id
- result_summary
- error_message

실제 구현 단계에서는 모델 설계를 다시 검토한다.

---

# 13. Local Scheduler

개발 편의를 위해 Local 환경에서는 코드 기반 Scheduler를 사용할 수 있다.

하지만 주석 처리를 통해 Scheduler를 켜고 끄지 않는다.

환경변수를 사용한다.

예:

LOCAL_SCHEDULER_ENABLED=true

운영:

LOCAL_SCHEDULER_ENABLED=false

운영 환경에서는 DB 기반 Schedule을 사용한다.

---

# 14. Admin

Admin은 서비스 운영 기능을 담당한다.

초기에는 Django Admin을 활용할 수 있지만, 최종적으로는 Next.js 기반 자체 Admin을 만든다.

Admin 기능:

- Dashboard
- User Management
- Character Management
- Character Variant
- Spot
- Spawn Rule
- Event
- Community Report
- News
- Crawler
- Batch
- Notification

---

# 15. Crawl System

Crawler와 일반 API Server를 강하게 결합하지 않는다.

구조:

Scheduler
→ Task Queue
→ Crawler Worker
→ Parser
→ Normalize
→ Duplicate Check
→ DB

수집 데이터에는 Source를 반드시 기록한다.

예상 데이터:

- source
- source_url
- source_type
- title
- content
- thumbnail
- published_at
- collected_at
- hash

중복 체크를 위한 Hash 활용을 고려한다.

---

# 16. API

초기 API는 REST를 사용한다.

예:

GET /api/v1/spots/nearby

POST /api/v1/encounters

POST /api/v1/encounters/{id}/capture

GET /api/v1/collection

GET /api/v1/community/posts

POST /api/v1/community/posts

GET /api/v1/news

초기부터 GraphQL을 사용하지 않는다.

향후 복잡한 Aggregate 조회가 필요해졌을 때 일부 영역에서 GraphQL을 실험할 수 있다.

---

# 17. Authentication

OAuth 기반 Login을 고려한다.

예:

- Google
- Apple
- Kakao

JWT 기반 인증을 사용할 수 있다.

Web과 Mobile에서 모두 사용할 수 있는 구조를 고려한다.

---

# 18. Storage

이미지 및 Asset은 DB Blob으로 저장하지 않는다.

Object Storage를 사용한다.

예:

AWS S3

저장 대상:

- User Profile
- Community Images
- News Thumbnail
- Character Asset
- 3D Asset

---

# 19. Infrastructure

로컬 개발:

Docker Compose

Container:

Docker

CI/CD:

GitHub Actions

Cloud 환경은 AWS를 우선 고려한다.

후보:

- ECS
- ECR
- RDS
- ElastiCache
- S3
- CloudFront
- Load Balancer

초기 단계부터 Kubernetes를 사용하지 않는다.

서비스가 안정적으로 구성된 이후 학습 목적으로 Kubernetes / EKS를 추가할 수 있다.

---

# 20. Observability

단순히 기능만 구현하지 않는다.

실제 서비스 운영을 고려한다.

사용 후보:

- OpenTelemetry
- Prometheus
- Grafana
- Sentry

확인해야 할 정보:

- API Latency
- P95 Response Time
- Error Rate
- DB Connection
- Redis Cache Hit Ratio
- Celery Queue
- Worker Status
- Batch Failure
- Crawler Failure

로그에는 Trace ID를 포함하는 구조를 고려한다.

---

# 21. Testing

Backend:

- pytest
- pytest-django
- Factory Boy

Frontend:

- Vitest
- React Testing Library

E2E:

- Playwright

특히 단순 CRUD Test보다 비즈니스 Rule Test를 중요하게 생각한다.

예:

- 동일 Encounter 중복 Capture 불가
- 만료된 Encounter Capture 불가
- 허용 거리 밖 Capture 불가
- 비활성 Spot Encounter 불가
- 이벤트 종료 이후 Spawn 불가
- 중복 News 수집 방지
- Batch 중복 실행 방지

---

# 22. Architecture 원칙

처음부터 MSA로 만들지 않는다.

초기에는 Modular Monolith 방식으로 개발한다.

도메인 경계를 명확하게 유지한다.

향후 트래픽 특성이나 운영 특성이 명확히 달라지는 영역만 분리한다.

분리 후보:

- Spatial Service
- Crawler Service
- Notification Service
- Batch Worker

기술을 사용하기 위한 기술 선택은 하지 않는다.

모든 기술에 대해 다음 질문에 답할 수 있어야 한다.

왜 이 기술이 필요한가?

어떤 문제를 해결하는가?

대안은 무엇인가?

언제 이 기술을 제거해야 하는가?

---

# 23. 개발 철학

이 프로젝트의 가장 중요한 목표는 서비스 회사의 개발 방식에 익숙해지는 것이다.

단순히 화면 요구사항을 받고 CRUD를 구현하는 방식에서 벗어나 다음을 고려한다.

- Domain
- Business Rule
- Transaction
- Concurrency
- Cache
- Consistency
- Scalability
- Failure
- Retry
- Observability
- Deployment
- Operation

코드를 작성할 때 항상 운영 환경을 고려한다.

---

# 24. Codex 작업 원칙

Codex는 다음 원칙을 따른다.

## 임의의 대규모 구현 금지

한 번에 프로젝트 전체를 구현하지 않는다.

작은 단위로 진행한다.

## 변경 전 설명

큰 구조 변경 전에 다음을 설명한다.

- 변경 목적
- 선택 이유
- 장점
- 단점
- 다른 대안

## 과도한 자동 생성 금지

개발자가 학습하는 것이 프로젝트의 핵심 목적이다.

따라서 단순히 완성된 코드를 대량 생성하기보다는 구조와 의도를 이해할 수 있게 진행한다.

## 기존 구조 존중

이미 구현된 Architecture와 Naming을 먼저 확인한다.

임의로 구조를 변경하지 않는다.

## 새로운 Dependency

Library나 Framework를 새로 추가할 경우 반드시 다음을 먼저 설명한다.

- Library
- 사용 목적
- 대안
- 추가하는 이유

## 최신 방식 사용

Deprecated API 또는 오래된 Tutorial 방식은 피한다.

현재 사용 중인 Version을 먼저 확인한다.

## 복잡성 통제

필요하지 않은 추상화, Interface, Factory, Pattern을 무조건 추가하지 않는다.

현재 요구사항을 해결할 수 있는 가장 단순한 구조에서 시작한다.

---

# 25. 개발 진행 순서

프로젝트는 다음 단계로 진행한다.

## Phase 0

- Repository 구성
- Docker
- 개발환경
- 프로젝트 Convention
- Environment 설정

## Phase 1

- Domain 정의
- DB 기본 설계
- API Convention
- Django 기본 구조
- Next.js 기본 구조

## Phase 2

- Account
- Authentication

## Phase 3

- Character
- Character Variant

## Phase 4

- Spot
- PostGIS
- Nearby API

## Phase 5

- Spawn Rule
- Encounter

## Phase 6

- Capture
- Collection

여기까지를 첫 번째 핵심 MVP로 본다.

## Phase 7

- Community

## Phase 8

- Crawler
- News

## Phase 9

- Celery
- RabbitMQ

## Phase 10

- Batch Platform
- Batch Admin

## Phase 11

- Redis
- Cache
- Rate Limit
- Ranking

## Phase 12

- Flutter
- GPS
- Map

## Phase 13

- Push Notification

## Phase 14

- CI/CD
- Cloud Deployment

## Phase 15

- Monitoring
- Observability

## Phase 16

- Performance Test
- Load Test
- Bottleneck Analysis

## Future

- 3D
- Unity
- AR
- H3
- Kafka
- Kubernetes

이 기능들은 필요성이 확인된 이후 추가한다.

---

# 26. 가장 중요한 원칙

이 프로젝트의 목적은 기술 이름을 많이 사용하는 것이 아니다.

각 기술을 실제 문제 해결에 사용하고, 그 선택 이유를 설명할 수 있는 개발자가 되는 것이 목표다.

따라서 항상 다음 순서로 생각한다.

Problem
→ Requirement
→ Design
→ Implementation
→ Test
→ Measurement
→ Improvement

기술을 먼저 선택하고 문제를 끼워 맞추지 않는다.

---

# 27. 현재 작업 요청

이 문서를 프로젝트 전체 Context로 사용한다.

새로운 작업을 요청받으면 먼저 현재 Repository의 코드와 구조를 확인한다.

기존 구현과 충돌하지 않는 범위에서 작업한다.

현재 단계보다 지나치게 앞선 기능을 임의로 구현하지 않는다.

필요한 경우 다음 단계의 선택지를 제시할 수 있지만 사용자의 요청 없이 대규모 선행 구현은 하지 않는다.

그리고 사용자가 직접 구현하며 학습하는 것을 우선하므로, 가능한 경우 다음 순서로 지원한다.

1. 구현할 기능 설명
2. 설계 선택지
3. 추천 방향과 이유
4. 파일/모듈 구성
5. 구현할 순서
6. 필요한 핵심 코드
7. 테스트 방법

완성 코드를 무조건 한 번에 생성하기보다 개발자가 직접 따라갈 수 있도록 단계적으로 작업한다.