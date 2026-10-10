# CHII WORLD / ChiikawaGo

위치 기반 캐릭터 수집 서비스의 **Phase 0~9** 기반입니다. Django Modular Monolith, Next.js App Router, PostgreSQL/PostGIS를 사용합니다. 현재 기능은 이메일/JWT 인증, 캐릭터 카탈로그, Nearby API, Spawn Rule/Encounter, 멱등 Capture, 본인 Collection 목록, Community, 검수 기반 News 발행과 Celery/RabbitMQ 비동기 수집 및 Django Admin입니다. 첫 핵심 MVP를 API로 검증하며 모바일·지도·포획 화면은 후속 단계입니다.

## 설계 문서

먼저 [PROMPT.md](PROMPT.md)를 읽어 주세요.

- [제품과 MVP](docs/product.md)
- [도메인 경계](docs/domain.md)
- [아키텍처와 선택 이유](docs/architecture.md)
- [데이터 모델](docs/data-model.md)
- [API 규약](docs/api-convention.md)
- [단계별 개발·테스트 계획](docs/development-plan.md)

## 로컬 시작

Docker Engine/Desktop와 Compose v2가 필요합니다. Apple Silicon에서 PostGIS 이미지는 amd64 에뮬레이션을 사용합니다. 호스트에 Python/GDAL/Node를 설치할 필요는 없습니다.

```sh
cp .env.example .env
docker compose build
docker compose up -d --wait db
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py seed_demo
docker compose run --rm api python manage.py createsuperuser
docker compose up -d --wait
```

`createsuperuser`는 대화형으로 이메일·표시명·비밀번호를 받습니다. 기본 관리자 계정은 없습니다. `seed_demo`는 샘플 캐릭터·Variant·서울 Spot만 만들고 기존 데이터를 덮어쓰지 않습니다. migration과 샘플 등록은 서버 시작 때 자동 실행하지 않습니다.

- 웹: [localhost:3000](http://localhost:3000)
- 운영 데이터 관리: [localhost:8000/admin/](http://localhost:8000/admin/)
- OpenAPI: [localhost:8000/api/v1/schema](http://localhost:8000/api/v1/schema)
- 생존/DB 준비 상태: `/health`, `/ready`

`.env`는 커밋하지 않습니다. 예시 비밀번호/키는 격리된 로컬 전용입니다. 포트를 바꿀 때 WEB_PORT와 WEB_ORIGIN도 함께 변경하세요. Origin 검증 때문에 브라우저에서 localhost/127.0.0.1을 혼용하지 마세요.

웹에서 회원가입 후 로그인할 수 있습니다. 계정 화면은 서버 렌더링이며 Access가 만료되면 **로그인 연장**으로 계속 사용할 수 있습니다. Refresh가 만료되거나 재사용되면 재로그인이 필요합니다. JWT는 HttpOnly 쿠키이며 localStorage에는 저장하지 않습니다.

## API 사용

상세 입력과 오류 계약은 [API 문서](docs/api-convention.md)에 있습니다. 직접 클라이언트는 `/api/v1/auth/token`에서 받은 access를 Bearer로 전달합니다.

```sh
curl http://localhost:8000/api/v1/characters
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  'http://localhost:8000/api/v1/spots/nearby?latitude=37.5665&longitude=126.978&radius_m=1000'
```

Nearby는 활성 Spot만 거리 순으로 반환합니다. 검색 반경은 기본 1km, 최대 5km입니다. 사용자 좌표는 저장하지 않습니다. Spot/캐릭터의 추가·수정은 초기 Django Admin에서 수행합니다.

## 검사와 테스트

```sh
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
docker compose run --rm api python manage.py check
docker compose run --rm api python manage.py makemigrations --check --dry-run
docker compose run --rm api python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yaml
docker compose run --rm api pytest -q
docker compose run --rm web npm run lint
docker compose run --rm web npm run typecheck
docker compose run --rm web npm run test
```

백엔드 테스트는 실제 PostGIS 테스트 DB를 사용합니다. DB 서비스가 실행 중이어야 합니다. E2E는 전체 스택을 켠 뒤 Node 22 환경에서 실행합니다.

```sh
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
```

CI에서는 Chromium 시스템 의존성을 위해 `npx playwright install --with-deps chromium`을 사용합니다. E2E는 `e2e-<timestamp>@example.com` 테스트 계정을 만들므로 운영 DB에 실행하지 마세요.

개발 서버의 `.next` 볼륨과 충돌하지 않게 빌드는 별도 컨테이너에서 검사합니다.

```sh
docker run --rm chii-world-web npm run build
docker compose run --rm api python manage.py explain_nearby --count 10000
```

`explain_nearby`는 임시 샘플 데이터를 롤백합니다. 테스트 방법과 해석은 개발 계획 문서를 참고하세요.

## 일상 개발

```sh
docker compose logs -f api web
docker compose run --rm api python manage.py makemigrations
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py flushexpiredtokens
docker compose down
```

`down`은 DB 볼륨을 보존합니다. 데이터 삭제가 목적이 아니라면 `down -v`를 사용하지 마세요.

Backend 의존성 변경 후 uv.lock을 갱신하고 API 이미지를 재빌드합니다. Frontend 의존성 변경 후 package-lock.json을 갱신하고 web 이미지를 재빌드한 다음 기존 node_modules 볼륨에도 `docker compose run --rm web npm ci`를 적용합니다. 의존성 갱신은 서버를 멈춘 상태에서 수행하세요.

개발 서버/Compose는 운영 배포용이 아닙니다. Phase 9에서 수집용 Celery/RabbitMQ를 추가했습니다. Redis와 클라우드 배포는 포함하지 않습니다.

## Phase 9: 수동 실행과 비동기 수집

기존 `.env`에 `.env.example`의 `RABBITMQ_USER`, `RABBITMQ_PASSWORD`를 추가한다. 예시 비밀번호는 로컬 전용이며 공유 환경에서는 교체한다. 비밀번호는 URL에 직접 결합하지 않고 설정에서 인코딩한다.

```sh
docker compose build api worker
docker compose up -d db rabbitmq api worker web
docker compose exec api python manage.py migrate
# 동기 실행: broker가 없어도 사용 가능
docker compose exec api python manage.py collect_news --source dreamnews-dretec
# 비동기 실행: 발행 확인 및 task ID만 반환
docker compose exec api python manage.py enqueue_news_collection --source dreamnews-dretec
docker compose logs --tail=100 worker
```

수집은 Candidate까지만 생성한다. 검수·발행은 기존 Admin에서 수행한다. task ID 발급은 수집 완료가 아니다. 로그에서 같은 task ID의 started/retry/succeeded/failed를 확인한다. 실패한 task와 개별 Worker 실행 프로세스 강제 종료는 원인을 확인한 뒤 enqueue 명령으로 수동 재실행한다. 이미 수집된 항목은 중복 생성되지 않는다. Source 정책 차단을 우회해서 재실행하지 않는다.

RabbitMQ 관리 UI와 호스트 포트는 열지 않는다. queue 확인은 `docker compose exec rabbitmq rabbitmqctl list_queues -p chii name messages_ready messages_unacknowledged`를 사용한다. Result backend·상태 조회 API·영구 실행 이력은 없으며 Phase 10에서 검토한다. 일반 API는 broker 장애와 무관하게 실행된다.

기본 Backend 테스트는 RabbitMQ 연결 없이 실행하며 broker 그룹은 기본적으로 건너뛴다. 실제 통합 테스트는 다음처럼 명시적으로 실행한다. 테스트는 별도 PostgreSQL 테스트 DB와 고유 큐, 합성 HTML 응답을 사용하며 외부 사이트에 접속하지 않는다.

```sh
docker compose exec api pytest -q
docker compose exec -e RUN_BROKER_TESTS=1 api pytest tests/broker -m broker -q
```

DB commit과 메시지 발행은 원자적이지 않다. commit 직후 프로세스 종료로 접수가 누락될 수 있으므로 접수 실패를 확인해 수동 재실행한다. 일시 네트워크 오류만 최초 실행 외 최대 두 번 재시도하며, HTTP 403/429·정책·파싱·DB 오류는 재시도하지 않는다. 전체 Worker 연결 손실은 재전달될 수 있지만 개별 자식 프로세스 강제 종료의 자동 복구는 보장하지 않는다.
