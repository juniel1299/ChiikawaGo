# 시스템 아키텍처

## 기본 구조 — 확정

```text
Browser → Next.js (RSC + 필요한 Route Handler) → Django REST API → PostgreSQL/PostGIS
Operator → Django Admin ────────────────────────────────┘
API tests / future Flutter → Django REST API
Manual enqueue → RabbitMQ → Celery Worker → 기존 news 수집 서비스 → 동일 PostgreSQL
```

Django는 Modular Monolith다. 데이터·권한·게임 규칙의 최종 판단은 Django에 있고 Next.js는 DB에 접근하지 않는다. Web과 API가 별도 프로세스인 것은 표현 계층 분리이며 백엔드 MSA가 아니다.

## Repository와 실행 단위

```text
PROMPT.md / README.md / .env.example / compose.yaml
docs/                   # product, domain, architecture, data-model, api-convention, development-plan
backend/
  Dockerfile / pyproject.toml / uv.lock / manage.py
  config/               # urls, health, API 공통 규약, logging, settings
    settings/           # base, local, test, production
  apps/
    accounts/           # models/admin/serializers/views/urls/migrations
    characters/         # 모델과 공개 카탈로그
    spatial/            # 모델, Admin 좌표 입력, Nearby/상호작용 거리 selector
    encounters/         # Spawn Rule, 발급/Capture service, TTL/재사용, 결과 API/Admin
    collection/         # 획득 개체, 본인 목록, 조회 전용 Admin
    community/          # 게시글·댓글·좋아요·신고·moderation
    news/               # 수집·검수·발행, 동기 명령과 비동기 task
  tests/integration/
frontend/
  Dockerfile / package.json / package-lock.json
  src/app/              # App Router와 Route Handlers
  src/features/auth/    # 로그인 폼, 세션 제어 UI
  src/lib/server/       # 서버 전용 Django 호출과 쿠키
  src/lib/api/          # 브라우저 인증 요청
  tests/                # Vitest, Playwright
.github/workflows/      # 로컬과 같은 체크를 CI에서 실행
```

단일 저장소로 API·웹 계약 변경을 함께 검토한다. 각 app은 필요할 때 파일을 추가한다. 미래 도메인의 빈 디렉터리, 모바일 골격, 별도 admin app은 만들지 않았다.

## 기술과 대안

| 선택 | 이유 | 대안과 재검토 조건 |
|---|---|---|
| Django 5.2 LTS + DRF | ORM·migration·Admin과 REST를 한 생태계에서 학습 | FastAPI는 Admin/ORM을 별도 조합해야 하므로 현재 목적에 불필요 |
| Python 3.13, uv | 호환되는 런타임과 lock 기반 재현 | pip-tools도 가능하나 도구 혼용 금지 |
| Next.js 16 + React 19 + TypeScript | RSC/SSR과 웹 계층 학습 | Vite SPA는 현재 학습 목표와 다름 |
| Node 22 LTS + npm | 컨테이너와 CI의 동일 런타임, 단일 앱 의존성 관리 | pnpm workspace는 여러 JS 패키지가 생기면 검토 |
| Simple JWT | 발급·검증·갱신·blacklist의 검증된 구현 활용 | Django 세션은 더 단순하지만 JWT는 사용자 선택 |
| drf-spectacular | Serializer 기반 OpenAPI, 오류 형식은 후처리로 문서화 | 수기 계약의 이중 유지 비용 회피 |
| psycopg 3 | PostgreSQL 연결 | 직접 SQL은 필요한 공간 분석에만 사용 |
| PostGIS geography | 미터 기반 공간 반경·거리 조회, GiST 인덱스 | 단순 lat/lng와 Python 계산은 인덱스 활용이 어려움 |
| pytest / pytest-django | 실제 DB의 규칙·동시성 검증 | Django TestCase도 가능하나 fixture 조합을 통일 |
| Vitest / Testing Library / Playwright | UI 단위와 실제 브라우저·서버 연결 검증 | API mock만으로 인증 쿠키 검증을 대체하지 않음 |
| Ruff / ESLint + TS/Next 규칙 | 정적 오류와 일관된 규약 | 별도 Python formatter 중복 도입 없음 |

정확한 패키지 버전은 두 lock 파일에, 컨테이너 기반 이미지는 Dockerfile/Compose의 digest에 고정한다. Python 이미지는 3.13 계열, Node는 22 계열이다. `latest` 태그로 기반 이미지를 선택하지 않는다.

ESLint 10과 `eslint-config-next`의 하위 React 플러그인 호환 충돌을 확인했다. 구형 ESLint나 호환 shim 대신 `@next/eslint-plugin-next`, `typescript-eslint`, `@eslint/js`를 직접 조합한다. 전체 통합 설정으로 돌아가는 것은 그 하위 플러그인이 ESLint 10을 지원할 때 검토한다.

## Django 책임 배분

단순 CRUD는 generic view와 serializer로 처리한다. 복잡한 공간 조회는 `spatial/selectors.py`, Encounter 발급·만료 정리·Capture는 `encounters/services.py`에서 트랜잭션으로 처리한다. ORM 위의 범용 Repository는 없다. Custom User는 첫 migration부터 사용한다. Admin은 각 app의 `admin.py`로 등록한다.

로그에는 서버 발급 request ID, HTTP method, 일치한 route 패턴, 상태, 실행 시간을 넣는다. query string·요청 본문·토큰·사용자 좌표를 넣지 않는다. 로컬도 `DEBUG=False`로 민감한 디버그 페이지를 막고, Admin 정적 파일만 개발 서버의 `--insecure`로 제공한다.

## Next.js와 JWT

- 기본은 Server Component. 계정 페이지는 Django `/me`를 서버에서 직접 조회하고 `no-store`를 적용한다.
- 입력·클릭이 필요한 인증 UI만 Client Component다. RSC에서 자체 Route Handler를 다시 호출하지 않는다.
- 브라우저는 허용된 `/api/auth/{login,register,refresh,logout}`만 호출한다. 범용 프록시를 만들지 않았다.
- Django 토큰을 Next.js가 HttpOnly, SameSite=Lax, host-only 쿠키로 저장한다. Access 5분, Refresh 7일. 운영은 Secure이며 로컬 HTTP에서만 명시적으로 끈다.
- JWT는 localStorage, 클라이언트 상태, 브라우저 응답 JSON에 들어가지 않는다. Django 직접 API는 Bearer JWT를 지원한다.
- 웹 POST는 `WEB_ORIGIN`의 정확한 Origin과 CSRF header/cookie 쌍을 모두 검증한다. CSRF 쿠키도 HttpOnly이고 토큰은 same-origin GET 응답으로 전달한다.
- 쿠키 변경 요청은 탭 안에서 직렬화한다. Web Locks 지원 브라우저는 탭 사이도 직렬화한다. DB는 동일 Refresh의 중복 갱신을 잠금/blacklist로 방어한다.
- RSC 렌더 중 쿠키 갱신은 하지 않는다. 초기 웹은 만료 시 로그인 연장 버튼을 표시하고 Route Handler에서 갱신한다. 자동 갱신 UX는 후속이다.
- 로그아웃은 Refresh를 폐기하고 쿠키를 지운다. Access는 만료까지 유효할 수 있고, 비활성 계정은 즉시 거부한다.
- Admin은 Django 세션/CSRF를 유지한다. JWT와 혼용하지 않는다.

TanStack Query는 클라이언트 재조회가, Zustand는 화면 간 클라이언트 상태 공유가 필요해질 때 도입한다. ISR은 공개 콘텐츠에, Server Action은 적합한 폼에 추가한다. 지금은 Metadata·SSR·RSC·Route Handler를 실제 용도에만 사용한다.

## 로컬과 후속 인프라

Compose는 Web, API, PostgreSQL/PostGIS, RabbitMQ, Worker 다섯 서비스다. 소스 bind mount, DB named volume, 웹 node_modules/.next named volume으로 호스트 의존성을 분리한다. Python venv는 이미지 내부 `/opt/venv`다. 모든 외부 포트는 localhost에만 bind한다. 선택한 PostGIS 17/3.5 이미지는 amd64 전용이므로 Apple Silicon에서는 Docker Desktop 에뮬레이션을 사용한다.

Migration은 서버 부팅에 숨기지 않고 명령으로 적용한다. Redis는 TTL을 위해 도입하지 않는다. Celery/RabbitMQ는 Phase 9 수집 실행에 사용한다. Encounter 만료는 DB 시간 비교로 해결한다. Crawler/알림/이미지 작업이 생기면 비동기를, 측정된 병목이 생기면 캐시를 도입한다. Object Storage는 업로드 시 S3를 우선 검토하고 현재는 asset_key만 저장한다.

Kubernetes, Kafka, Unity/AR/3D, H3는 제외다. Prometheus/Grafana/OTel은 관측성 단계로 남긴다. production 설정은 안전한 기본값 초안이며 개발 Dockerfile·runserver를 운영 배포 구성으로 사용하지 않는다. 운영 WSGI/ASGI 서버, TLS proxy, 정적 파일/S3, 제한된 DB 역할은 Phase 14에서 결정한다.

## 공식 근거

- [Django 5.2 LTS](https://docs.djangoproject.com/en/5.2/releases/5.2/)
- [Next.js BFF: Server Component는 원본에서 직접 조회](https://nextjs.org/docs/app/guides/backend-for-frontend)
- [Simple JWT blacklist](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/blacklist_app.html)
- [GeoDjango geography 모델](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/model-api/)


Phase 6 Capture는 Encounter만 잠그고 성공 기록·Collection 생성을 명시적인 서비스 호출로 같은 트랜잭션에 묶는다. collection 서비스는 Encounter에서 소유자와 Variant를 결정한다. Capture 시 위치 재검증은 하지 않는다. Redis·추가 인프라·범용 Repository 없이 OneToOne 제약과 행 잠금으로 중복 지급을 막는다. Collection의 단순 목록은 generic view queryset과 select_related로 처리한다.

## Phase 9 — 비동기 수집 실행 계층

기존 API는 수집을 실행하지 않는다. 동기 collect_news 명령은 유지하고 enqueue_news_collection → RabbitMQ → 별도 Celery Worker → 동일 crawler.collect 함수 경로를 추가한다. task는 UUID만 받고 실행·재시도·안전한 로그를 담당한다. Parser/DB 로직을 task에 복제하지 않는다. 동일 Django 코드와 DB를 사용하는 Modular Monolith다.

Celery 5.6.3과 RabbitMQ 4.3.6 기본 이미지(관리 UI 없음)를 사용한다. 단일 durable classic news.collect queue, persistent JSON 메시지, publisher confirm을 사용하며 pickle·result backend·Flower·Redis·Beat·Batch 모델은 없다. Worker는 별도 backend 컨테이너의 prefork/concurrency 1, prefetch 1이다. soft/hard 제한은 600/660초, 종료 유예는 700초다. RabbitMQ는 내부 포트와 전용 사용자/vhost, named volume을 사용한다. API readiness는 broker와 결합하지 않는다.

DB commit 이후에만 on_commit으로 발행한다. commit과 publish 사이 crash 누락은 outbox 없이 보장할 수 없으며 수동 재실행 대상이다. late ACK를 사용하되 일반 실패와 개별 자식 프로세스 비정상 종료는 ACK하고 자동 requeue하지 않는다. Worker 전체 연결 소실로 재전달되면 기존 unique와 항목별 atomic으로 중복을 방지한다. 이미 커밋한 항목은 유지되고 진행 중인 항목만 rollback한다.

RabbitMQ 4.3 호환을 위해 Celery control/event queue는 exclusive로 명시한다. 수집 작업 큐는 durable classic을 유지한다. [Celery 설정](https://docs.celeryq.dev/en/v5.6.3/userguide/configuration.html#control-queue-exclusive)

## Phase 10 — DB Batch Platform

Next.js `/batch` → 허용된 BFF Route Handler → Django Batch API → PostgreSQL 원장 → RabbitMQ `batch.execute` → 동일 Backend Worker → News/Accounts 서비스로 연결한다. 최초 화면은 RSC가 Django를 직접 조회한다. 변경은 기존 JWT HttpOnly 쿠키·Origin/CSRF 검증을 사용한다. 화면이 보이는 동안 10초마다 갱신하고 TanStack Query/Zustand는 추가하지 않는다.

별도 `run_batch_scheduler` 프로세스는 5초마다 DB의 due Schedule과 발행 대기를 확인한다. Compose의 scheduler profile을 명시적으로 켠다. 로컬과 운영 모두 DB Cron을 사용하므로 LOCAL_SCHEDULER_ENABLED나 코드 Cron은 없다. 최근 정상 tick 파일로 health를 확인한다. RabbitMQ 장애는 기존 API readiness와 결합하지 않는다.

Execution을 전달 의도로 사용해 on_commit 누락을 복구한다. 별도 outbox/beat/result backend는 없다. croniter 6.2.4만 추가해 Cron 날짜/윤년/이전·다음 계산을 재사용한다. DST 지역·다중 Schedule·Source 병렬 실행·이력 자동 정리·자동 장애 판정은 후속이다.


## Phase 11 — Redis 도입 판단 완료

**C — Redis adoption deferred after measurement**로 확정했다. [로컬 baseline 보고서](../benchmarks/redis-evaluation/REPORT.md)의 PostGIS/count/JIT 및 Docker 자원 제약을 먼저 검토한다. 운영 capacity나 실제 cache hit rate를 검증한 결과는 아니다. Redis dependency·service·cache backend를 추가하지 않는다.

Batch 잠금은 PostgreSQL, Celery broker는 RabbitMQ, 실행 상태는 BatchExecution, JWT blacklist와 Django session은 기존 저장 구조를 유지한다. 로그인/공개 API rate limiting은 별도 abuse protection 요구이며 proxy/gateway와 향후 다중 인스턴스 요구를 기준으로 검토한다. 성능 최적화 추가 구현은 이번 결정에 포함하지 않는다.
