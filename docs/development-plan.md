# 개발 순서와 검증

## 현재 범위

승인된 Phase 0~4를 단계별로 구성했다. 첫 MVP는 Phase 6까지이므로 Encounter·Capture·Collection은 아직 없다. 코드의 의도는 각 도메인 문서에, 로컬 실행 명령은 README에 둔다. 실제 검증 결과와 남은 한계는 아래에 별도로 기록한다.

| 단계 | 구현 순서와 산출물 | 완료 기준 |
|---|---|---|
| 0 | PROMPT 보존 → 문서 → 버전·lock → env/ignore → 부트스트랩 → Docker/Compose → 실행 안내 | 새 환경에서 Web/API/PostGIS 실행, 비밀값 제외 |
| 1 | 도메인 소유권 → 설정 분리 → Custom User → PostGIS migration → App Router → API 오류/OpenAPI → 테스트/CI | migration, health/readiness, 웹 렌더링, 오류 계약 |
| 2 | 가입/비밀번호 → JWT 발급 → rotation/blacklist → me/비활성 계정 → 웹 인증 → CSRF/동시성 검증 | 직접 API와 브라우저 인증 수명주기 |
| 3 | Character/Variant → Admin → 공개 조회 → 샘플 명령 → 제약 테스트 | 기본형/Variant 관리와 공개 활성 카탈로그 |
| 4 | Spot/GiST → Admin 좌표 → selector → Nearby → 공간 경계 → EXPLAIN | 실제 PostGIS 거리·반경·비활성 필터·실행계획 |

Phase 0은 환경 구동에 필요한 최소 부트스트랩, Phase 1은 그 내부 도메인·설정 구조다. 빈 미래 app, 자동 관리자 생성, 초기 업로드 인프라를 추가하지 않았다.

## 환경 규약

- 기반: Python 3.13, Django 5.2 LTS, Node 22 LTS, Next.js 16, PostgreSQL 17/PostGIS 3.5.
- pyproject/package.json에서 직접 의존성을 고정하고 uv.lock/package-lock.json도 커밋한다.
- 런타임 기반 이미지는 tag와 digest를 함께 기록한다. 업데이트는 버전 변경·이미지 재빌드·같은 검증을 한 변경으로 수행한다.
- Compose의 `db`는 named volume, `api`는 이미지 내부 venv, `web`은 별도 node_modules/.next volume을 사용한다.
- `.env.example`의 로컬 예시를 `.env`로 복사한다. `.env`는 Git과 이미지 context에서 제외한다.
- migration/관리자/샘플 등록은 명시적 명령이다. 컨테이너 부팅으로 운영 데이터를 변경하지 않는다.
- API_SECRET과 JWT signing key 역할을 분리한다. 실제 변수명은 `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`다.
- `WEB_ORIGIN`은 브라우저 주소와 정확히 일치해야 한다. localhost와 127.0.0.1을 혼용하지 않는다.
- 현재 운영 scheduler가 없으므로 `LOCAL_SCHEDULER_ENABLED`도 아직 추가하지 않는다.

## 검증 시나리오

### Backend

pytest/pytest-django가 실제 PostGIS 테스트 DB를 생성한다. SQLite 대체 금지.

- 빈 DB migration, PostGIS extension, health, DB 장애 readiness 503.
- 이메일 대소문자 중복·DB 우회 삽입, 비밀번호 검증·해시, 권한 필드 주입 무시.
- 잘못된 비밀번호, 만료 Access, 비활성 User, rotation, refresh 재사용, 로그아웃 후 갱신 실패.
- 두 스레드의 동시 refresh에서 하나만 성공.
- 공개 카탈로그 활성 필터, 비활성 부모, Variant 유일/등급 제약, Character 삭제 보호.
- PostGIS 기준 반경 안·밖·경계, 거리 오름차순/동률 UUID, NaN/Infinity, 잘못된 좌표·반경, 인증, 빈 결과.
- Admin 좌표 입력과 Point 순서, 공간 인덱스와 쿼리 함수 존재.
- OpenAPI 생성·유효성, request_id와 로그의 위치/토큰 비노출.

### Frontend

Vitest/Testing Library는 폼 오류·이동, CSRF와 쿠키 속성을 검증한다. Playwright는 실제 Django와 연결된 Web에서 가입·로그인·JWT 비노출·갱신·만료 상태 복구·로그아웃 및 CSRF 거부를 검증한다. API mock만으로 전체 인증을 대체하지 않는다.

`npm run build`로 Server Component/Route Handler의 production 빌드를 확인한다. 빌드 성공이 운영 배포 완료를 의미하지는 않는다.

### 공간 실행계획

`manage.py explain_nearby --count 10000`은 임시 1만 Spot을 생성하고 ANALYZE 후 `EXPLAIN (ANALYZE, BUFFERS)`를 출력한다. 마지막에 삽입을 롤백하므로 실제 Spot 데이터는 보존한다. 샘플 데이터/좌표가 제한된 개발 실험이며 부하 테스트나 P95 측정을 대신하지 않는다. 작은 테이블의 순차 스캔을 실패로 간주하지 않는다.

## CI와 후속 단계

GitHub Actions는 동일 Compose DB, backend 정적 검사/migration/schema/pytest와 frontend lint/typecheck/unit/build/E2E를 실행한다. 워크플로 파일을 제공했으며 원격 실행 여부는 실제 Actions 결과에서 확인한다. 클라우드 배포는 Phase 14다.

1. **Phase 5:** Spawn 조건·시간·확률 결정, Encounter 발급/만료 설계와 테스트.
2. **Phase 6:** Capture 원자성·중복 결과 재사용, Collection 조회. 이 시점이 첫 핵심 MVP 완료.
3. **Phase 7:** Community와 권한·신고.
4. **Phase 8:** Crawler의 수집/정규화/중복/검수 흐름을 수동 실행 가능한 유스케이스로 먼저 완성.
5. **Phase 9:** Celery + RabbitMQ 연결. HTTP와 수집 작업을 분리.
6. **Phase 10:** DB 기반 Schedule, Batch Job/Execution, 관리 화면. Python에 운영 Cron을 하드코딩하지 않음.
7. **Phase 11:** Redis가 필요한 병목/캐시/분산 요청 제한을 측정 후 기능별 도입.
8. **Phase 12~16:** Flutter/GPS/Map → Push → Cloud CI/CD → Monitoring → 부하/병목 분석.

각 작업은 기능 설명 → 선택 이유 → 작은 구현 → 핵심 테스트 → 측정/검토 순서다. Repository/Interface/Factory/DDD 추상화는 실제 복잡성이 생길 때만 추가한다.

## 공개 운영 전 남은 사항

개발 Compose는 운영 배포 구성이 아니다. 이메일 소유 확인/재설정, 로그인 요청 제한, TLS/보안 origin, 최소 권한 DB, 운영 서버/정적 파일 배포와 보관 정책은 공개 운영 단계에서 검토한다. 초기 범위에 Redis·별도 인증 서비스·클라우드를 임의로 추가하지 않는다. 만료 token 테이블 정리는 당분간 `flushexpiredtokens` 수동 명령이며 추후 DB 관리 Batch에 등록한다.

## 2026-10-02 로컬 검증 기록

- Docker Desktop / Apple Silicon에서 Compose 세 서비스 구동 및 migration 적용.
- 실제 PostGIS의 Backend 테스트 23개, Vitest 4개, 실제 스택의 Chromium E2E 2개 통과.
- Django system check, migration drift, OpenAPI validate/fail-on-warn, Ruff, ESLint, TypeScript 검증 통과.
- Node 22 컨테이너에서 Next.js production build 성공.
- 1만 임시 Spot의 실행계획에서 location GiST의 Bitmap Index Scan 확인. 표본 실행 약 53ms는 에뮬레이션 환경의 단일 측정이므로 성능 보장값이 아니다.
- 데스크톱 홈/390px 모바일 가입 화면을 확인했고 가로 넘침이 없었다.
- GitHub Actions 워크플로는 작성했으나 원격 CI 실행·운영 배포는 이번 작업 범위에 포함하지 않았다.

## 2026-10-02 MUST FIX 3건 수정 후 검증

이번 변경은 Refresh/Logout 잠금, 인증 성공 OpenAPI 응답, 내부 예외 로그에 한정한다. API URL/payload와 JWT 수명·rotation·blacklist 정책을 유지하며 의존성·migration·Phase 5 기능은 추가하지 않았다.

- Refresh와 Logout 모두 트랜잭션 밖에서 토큰을 검증한 다음 OutstandingToken을 잠그고, 잠금 획득 후 만료/blacklist를 다시 검증한다. 처리 도중 실패하면 blacklist와 새 토큰 저장을 함께 롤백한다. deadlock retry는 추가하지 않았다.
- 로그인과 Refresh의 성공 응답을 필수 문자열 `access`, `refresh`로 명시했다. 실제 성공 응답과 OpenAPI의 필드·타입·required를 비교하는 계약 테스트를 추가했다.
- 내부 오류는 클라이언트에 기존 일반화된 500을 반환한다. 서버는 request ID, 예외 타입, 안전한 대체 메시지, 파일/함수/행 번호 스택과 연결된 예외를 기록한다. 예외 메시지 원문·notes·소스 코드 행·지역변수는 기록하지 않으며 DB 오류도 허용된 SQLSTATE의 고정 설명만 사용한다.

검증 결과:

| 검증 | 결과 |
|---|---|
| Backend 전체 | 실제 PostgreSQL/PostGIS에서 35개 통과 (기존 23개 + 신규 12개) |
| 동시성 | Refresh 선점/Logout 선점/Refresh 간 경합 모두 PostgreSQL `pg_blocking_pids`로 실제 잠금 대기 확인 후 성공·실패 응답과 최종 DB 상태 검증 |
| 롤백 | blacklist 기록 후 및 새 OutstandingToken 저장 후 실패 주입: 부분 변경 없음 |
| 오류 로그 | DRF 및 Django 500 처리, 포맷된 로그의 request ID/스택, 연결된 예외·DB 오류의 민감값 비노출 검증 |
| Frontend unit | Vitest 4개 통과 |
| E2E | 실제 개발 스택의 Chromium 2개 통과: 가입/로그인/갱신/만료 복구/로그아웃 및 CSRF |
| OpenAPI | 실제 성공 응답 계약 테스트 및 `spectacular --validate --fail-on-warn` 통과 |
| 정적 검사 | Ruff check/format, Django check, ESLint, TypeScript 통과 |
| Production build | 별도 Node 22 컨테이너의 Next.js build 성공 |
| Migration drift | `makemigrations --check --dry-run`: 변경 없음 |

위 결과는 로컬 검증이다. 원격 GitHub Actions는 실행하지 않았다. E2E는 기존 개발 서버 대상으로 실행했고 production build와 별도로 검증했다.

이번에 수정하지 않은 SHOULD FIX: Logout의 403/401 차이와 BFF의 4xx 처리, BFF 자체 오류 envelope 통일, Admin 권한/프런트엔드 오류 상태 테스트 확대, production E2E 및 CI 실패 artifact 보관. 공개 운영 전 보안·운영 항목은 위 기존 목록을 유지한다.

세 MUST FIX와 회귀 검증이 완료되어 Phase 5의 Spawn Rule/Encounter 구현에 착수할 수 있다. 이는 공개 운영 준비 완료를 의미하지 않으며 Phase 5의 게임 규칙·트랜잭션·동시성 검증은 해당 단계에서 추가한다.
