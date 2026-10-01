# CHII WORLD / ChiikawaGo

위치 기반 캐릭터 수집 서비스의 **Phase 0~4** 기반입니다. Django Modular Monolith, Next.js App Router, PostgreSQL/PostGIS를 사용합니다. 현재 기능은 이메일/JWT 인증, 캐릭터 카탈로그, Nearby API와 Django Admin입니다. Encounter·Capture·Collection은 Phase 5~6입니다.

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

개발 서버/Compose는 운영 배포용이 아닙니다. Redis, Celery, RabbitMQ와 클라우드는 아직 필요하지 않아 추가하지 않았습니다.
