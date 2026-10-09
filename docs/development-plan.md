# 개발 순서와 검증

## 현재 범위

승인된 Phase 0~6을 단계별로 구성했다. 첫 핵심 MVP는 API 통합 테스트와 Django Admin 기준으로 검증한다. 코드의 의도는 각 도메인 문서에, 로컬 실행 명령은 README에 둔다. 실제 검증 결과와 남은 한계는 아래에 별도로 기록한다.

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

1. **Phase 5:** 정수 weight·단일 기간 Rule, Encounter 발급/자연 만료/재사용, 조회 전용 Admin 구현.
2. **Phase 6:** Capture 원자성·중복 결과 재사용, Collection 조회 구현. API/Admin 기준 첫 핵심 MVP.
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


## Phase 5 구현과 운영 범위

SpawnRule은 Admin에서 생성·수정·활성/비활성화한다. 생성 후 Spot/Variant 관계는 변경하지 않으며, 삭제·일괄 action은 없다. 동일 조합은 unique이므로 비활성 Rule이 이미 있으면 해당 Rule의 기간·weight·활성 상태를 수정한다. Encounter Admin은 superuser를 포함해 조회만 가능하며, 실효 상태 필터는 expires_at까지 반영한다.

테스트는 실제 PostgreSQL/PostGIS를 사용한다. 최초 발급·만료 후 재발급·사용자 분리·Rule 변경 경합을 별도 연결과 pg_blocking_pids로 검증한다. 난수 구간은 반환값을 제어하며 시간 대기나 확률적 성공에 의존하지 않는다. GPS 거리 경계는 PostGIS 좌표 변환의 미세한 오차를 고려해 측정 경계의 양옆을 검증하고, 운영 반경에 보정값을 추가하지 않는다.

이 단계는 API와 Django Admin으로 완료한다. 프런트엔드·지도·모바일·Capture·Collection은 추가하지 않으며 새 라이브러리·캐시·큐도 없다. 배포 시 기존 migration 이후 encounters의 첫 migration을 명시적으로 적용한다. 운영 데이터 자동 생성은 없다.

## 2026-10-03 Phase 5 로컬 검증 기록

- Backend 전체 110개 통과: 기존 35개 + Phase 5 신규 75개. 실제 PostgreSQL/PostGIS 테스트 DB에서 빈 DB migration부터 검증했다.
- 신규 검사에는 Rule 기간/weight/DB 제약, 실제 JWT와 JSON 요청, 거리 경계, 카탈로그 필터, TTL 읽기/재사용/재발급, 소유권, Admin 읽기 전용 권한, OpenAPI 실제 응답 계약이 포함된다.
- PostgreSQL 잠금 대기를 확인한 최초 발급/만료 후 재발급/다른 사용자 경합과 Rule 비활성화 선점 순서, 잠금 대기 중 Rule 만료 테스트가 통과했다. 다른 Spot은 한 Spot의 잠금과 독립적으로 발급 가능함을 확인했다.
- 기존 Encounter 만료 상태 저장 후 실패 및 새 Encounter 저장 후 실패를 주입해 전체 롤백을 확인했다. Rule이 없어 재발급에 실패할 때도 기존 행을 부분 변경하지 않는다.
- Ruff check/format, Django check, OpenAPI validate/fail-on-warn, migration drift 검사 통과.
- 로컬 개발 DB에 encounters.0001_initial 적용 완료. migration은 신규 테이블과 제약만 생성한다.
- 기존 Frontend Vitest 4개, 실제 개발 스택 Chromium 인증/CSRF E2E 2개, ESLint/TypeScript 통과. 별도 Node 22 컨테이너에서 Next.js production build 성공.
- 코드 의존성·Compose·Frontend 기능 변경 없음. 타입 생성기의 next-env.d.ts 자동 변경은 복원했다. 원격 GitHub Actions는 실행하지 않았다.

Phase 5의 API/Admin 구현과 회귀 검증이 완료됐다. 동일 Spot 요청 직렬화, 사용자 입력 GPS의 한계, 저장 status와 실효 만료 상태의 차이는 설계상 유지된다. Phase 6 Capture/Collection, 공개 운영 준비 및 이전 SHOULD FIX는 이번 단계에서 구현하지 않았다.


## Phase 6 구현 범위와 검증

Capture는 위치 재검증 없이 유효한 Encounter를 성공 처리한다. 결과 → Collection → captured 변경을 하나의 트랜잭션으로 처리하며, 동일 Encounter 재시도는 TTL 이후에도 같은 결과를 반환한다. Collection은 현재 카탈로그 이름/등급을 조회하고, 기본 20/최대 100 pagination과 획득 시각/id 내림차순을 제공한다. Encounter/CaptureResult/Collection은 superuser도 Admin에서 조회만 가능하다.

기존 110개 검사 중 captured를 잘못된 status로 취급하던 Phase 5 케이스는 새 상태 정책에 맞춰 제거하고 Capture 상태 전이 테스트로 대체한다. 신규 검증은 실제 JWT/전체 MVP 흐름, 멱등성, 잠금 대기와 만료, 생성/Capture 경합, 저장 단계 전후 실패 주입, DB 유일 제약, 조회 권한/페이지/N+1, Admin, OpenAPI 계약, Phase 5 데이터 migration 보존을 포함한다.

Capture Rate·아이템·쿨다운·Redis·비동기·모바일은 추가하지 않는다. 같은 Spot에서 Capture 직후 다시 Encounter를 발급받을 수 있다. 공개 운영 보안 항목과 기존 SHOULD FIX는 별도 작업으로 남긴다.

## 2026-10-03 Phase 6 로컬 검증 기록

- Backend 전체 154개 통과. Phase 5의 110개 중 captured 금지 케이스 1개를 새 정책에 맞춰 대체하고, Phase 6 테스트 45개를 추가했다.
- 실제 PostgreSQL/PostGIS에서 동시 Capture의 동일 응답/단일 지급, 실패한 선행 요청의 재시도, 잠금 대기 중 만료, 생성/Capture 양방향 경합과 다른 Encounter의 독립 처리를 검증했다.
- CaptureResult 저장 후, Collection 저장 전/후, Encounter 상태 저장 전/후 예외를 주입해 전체 rollback을 확인했다. 불일치 데이터에는 자동 복구나 추가 지급 없이 500을 반환한다.
- 가입/로그인 → Nearby → Encounter → Capture → Collection 통합 흐름과 같은 Variant 반복 획득 검증 통과. 현재 카탈로그 반영·권한·pagination·동률 정렬 및 목록 count/page의 2개 쿼리로 N+1 방지 확인.
- 실제 Capture 최초/재시도·Collection 응답의 OpenAPI 필드/타입/required 검증, 읽기 전용 Admin과 captured 필터 검증 통과.
- 빈 DB migration 및 Phase 5 데이터를 둔 상태의 Phase 6 업그레이드 테스트 통과. 기존 Encounter 상태/시각 보존과 자동 지급 없음 확인. 로컬 개발 DB에도 encounters.0002 및 collection.0001 적용 완료.
- Ruff check/format, Django check, migration drift, spectacular --validate --fail-on-warn 통과.
- Frontend Vitest 4개, 실제 개발 스택 Chromium 인증/CSRF E2E 2개, ESLint/TypeScript 통과. 별도 Node 22 컨테이너 Next.js production build 성공.
- 의존성·Compose·Frontend 기능 변경 없음. 타입 생성기의 next-env.d.ts 자동 변경은 복원했다. 원격 GitHub Actions·커밋·push는 실행하지 않았다.

API 통합 테스트와 Django Admin 기준 첫 핵심 MVP가 완성됐다. 모바일/지도/포획 UI와 공개 운영 준비 완료를 뜻하지 않는다. 기존 SHOULD FIX, 운영 요청 제한과 탈퇴/익명화 정책은 후속 과제로 유지한다.

## Phase 7 — Community 구현

- community app 하나로 고정 Category, Post, 평면 Comment, 멱등 Like, Post/Comment Report 및 권한을 구현한다. API/Admin만 대상이다.
- 제한적 삭제는 본문 제거·댓글 삭제 처리·Like 제거를 하나의 트랜잭션에 묶는다. pending 신고 스냅샷만 보존하고 처리 시 제거한다. 운영자는 사용자 원문을 편집하지 않는다.
- Post 선행 잠금과 DB unique/check를 결합한다. 잠금 대기를 pg_blocking_pids로 확인하며 Like/Report 중복, 삭제/댓글 작성, 수정/신고, 삭제/신고 처리 경합 및 실패 롤백을 검증한다.
- 목록은 select_related·독립 집계 Subquery·Exists로 N+1과 조인 count 중복을 방지한다. 실제 응답/OpenAPI, Admin 권한/CSRF, Phase 6 데이터 보존 migration도 검증한다.
- 기존 Phase 5~6 변경은 체크포인트 9619a0c6에 분리했다. Phase 7 migration은 신규 community 테이블만 생성하고 기존 migration을 변경하지 않는다. 실행은 `docker compose exec api python manage.py migrate`로 명시한다.

운영상 한계: 같은 Post 변경 직렬화, page-number 페이지 이동, 미처리 신고의 기한 없는 증거 보관, 계정 탈퇴/익명화 미구현. 대댓글·이미지·분류 관리·Spot 연결·검색·보관 기한 자동화는 후속 고려사항이다. Redis/큐/새 라이브러리/Frontend 기능/기존 SHOULD FIX는 이번 범위에 없다.

## 2026-10-04 Phase 7 로컬 검증 기록

- Backend 전체 **203개 통과**: 기존 154개 + Community 49개. 실제 PostgreSQL/PostGIS 테스트 DB를 사용했다.
- pg_blocking_pids로 실제 잠금 대기를 확인한 중복 Like/취소/Report, 삭제와 댓글 작성, 수정과 신고 스냅샷, 삭제와 신고 처리의 양방향 경합이 통과했다. 다른 Post 변경은 독립적으로 진행했다.
- 삭제 중 실패, 신고 생성 직후 실패와 후속 재시도, 증거 제거 저장 전/후 실패에서 부분 변경 없이 롤백됨을 확인했다.
- UUID/enum/삭제/대상 XOR/unique/처리 증거 제약, 작성자 권한과 비활성 계정, 신고 원문·설명의 로그 비노출, 목록 집계·정렬·pagination·N+1 검증을 통과했다. 공개 Post 목록은 2개, Comment 목록은 3개 쿼리로 항목 수에 따라 증가하지 않는다.
- 실제 API 응답과 OpenAPI의 필드/타입/required, 204 빈 응답 및 공통 오류 계약 검증을 통과했다. 관리자 읽기 전용, 권한 분리, 실제 CSRF를 사용하는 일반 운영자의 처리, 증거 제거와 삭제 복원 금지를 확인했다.
- 빈 DB migration과 Phase 6 Capture/Collection 데이터를 보존하는 업그레이드 테스트 통과. 로컬 개발 DB에 community.0001_initial 적용 완료.
- Ruff check/format, Django check, migration drift, spectacular --validate --fail-on-warn 통과.
- Frontend Vitest 4개, ESLint/TypeScript, 별도 Node 22 컨테이너의 Next.js production build 통과. 개발 스택 대상 Chromium 인증/CSRF E2E 2개 통과(브라우저 테스트 runner는 호스트 Node 23.7.0, Web 서버는 Node 22).
- 타입 생성으로 변경된 next-env.d.ts는 원래 내용으로 복원했다. 의존성·Compose·Frontend·기존 도메인 기능 변경 없음. 원격 GitHub Actions는 실행하지 않았다.
- Phase 5~6 체크포인트 커밋만 생성했다. Phase 7 변경은 아직 commit/push하지 않았다.

Phase 7 API/Admin MVP의 완료 조건을 충족한다. 공개 운영 준비나 Community 웹 UI 완료를 의미하지 않는다. 미처리 신고 증거 보관과 Post 단위 직렬화는 위 설계상 한계로 유지한다.


## Phase 8 — 구현 및 운영 규약

Phase 7 체크포인트 2aca73c8을 feat/spawn-encounter에 push한 뒤 feat/crawler-news에서 구현한다. Source를 Admin에서 dreamnews-dretec / dreamnews_dretec으로 등록하고 정책 확인 시각과 메모를 입력한 뒤 활성화한다. `docker compose exec api python manage.py collect_news --source dreamnews-dretec`로 수동 실행한다. 하루 한 번 실행을 운영 기본으로 하며 자동 스케줄은 없다.

robots 확인 → 목록 첫 페이지 → 치이카와 상품 상세 최대 5개 → 정규화 → 중복 확인 → Candidate → Admin 승인/반려 → 공개 News 순서다. HTTP 사이 최소 10초, timeout 10초, 응답 상한 2MiB, 명시적 User-Agent와 호스트/경로 제한을 적용한다. 403/429/challenge를 우회하거나 자동 재시도하지 않는다. 항목별 실패는 롤백하고 다른 성공은 보존하며, 실패가 있으면 명령은 비정상 종료한다.

자동 테스트는 최소 HTML/JSON-LD fixture와 고정 응답만 사용한다. 실제 사이트에 CI가 의존하지 않는다. DB 제약·동시 잠금·rollback·발행 불변성·Admin·API 계약·N+1·Phase 7 migration 보존을 실제 PostGIS에서 검증한다. 실제 사이트 확인은 별도 제한된 수동 실행이며 자동 승인하지 않는다. 상업화, 본문/이미지, revision·재검수·비동기·Batch는 후속이다.


### Phase 8 로컬 실행 안내

1. `docker compose exec api python manage.py migrate`로 news.0001_initial을 적용한다.
2. Admin의 Source에서 code=`dreamnews-dretec`, adapter=`dreamnews_dretec`, 이름, 정책 확인 시각·메모를 등록하고 활성화한다. 고정된 목록/정책 URL은 변경하지 않는다. 기본 비활성이며 migration은 Source를 자동 생성하지 않는다.
3. `docker compose exec api python manage.py collect_news --source dreamnews-dretec`를 명시적으로 실행한다. 출력은 created/skipped/failed이고 실패가 있으면 비정상 종료한다. 네트워크·정책 오류의 경우 우회하지 말고 Source와 사이트 상태를 확인한다.
4. NewsCandidate Admin에서 출처를 확인하고 별도 검수 권한으로 승인/반려한다. 승인은 즉시 발행한다. GET /api/v1/news에서 확인한다.

동일 adapter의 Source를 하나로 제한해 요청 간격을 공유한다. 운영자 Source 수정은 진행 중인 요청 예약 시각을 보존한다. 지원하지 못하는 robots 규칙(와일드카드 경로·Allow 우선순위·10초 초과 crawl-delay 포함)이 나타나면 추측해서 진행하지 않고 중단한다. HTTP timeout은 소켓 연결/읽기 기준 10초이며 실행 전체 제한 시간이 아니다. 검수 전 공개 API에는 나타나지 않는다.

## 2026-10-09 Phase 8 로컬 검증 기록

- Phase 7 체크포인트 **2aca73c8** (`feat: complete community api and moderation`)을 기존 origin의 feat/spawn-encounter에 push했다. 현재 feat/crawler-news는 이 체크포인트를 기반으로 한다. Phase 8 변경은 아직 commit/push하지 않았다.
- 실제 PostgreSQL/PostGIS에서 Backend 전체 **276개 통과**: 기존 203개 + News 신규 73개. 동시 수집·승인/반려·실패 후 재시도·요청 예약과 Source 비활성화 경합에서 pg_blocking_pids로 실제 대기를 확인했다.
- RawItem/Candidate 저장 및 News/검수 상태/audit 저장 실패 주입의 rollback, published/pending/rejected 모두 재수집 불변, DB unique/check, Phase 7 콘텐츠·Capture/Collection 보존 migration을 검증했다.
- 고정 HTTP 응답 → 실제 fetch/rate gate → parser → 정규화 → Candidate → 검수 → 공개 API 통합 검증을 통과했다. CI 테스트는 실제 사이트에 요청하지 않는다. 기본 parser fixture는 실제 구조를 반영한 합성 텍스트이며 원문 본문을 복제하지 않는다.
- 공개 News 실제 응답/OpenAPI 필드·타입·required, category/pagination/동률 정렬, 목록 2개·상세 1개 쿼리, Admin 권한/CSRF/읽기 전용/출처 정책 강제 검증 통과.
- Ruff check/format, Django check, migration drift 및 spectacular --validate --fail-on-warn 통과. Community의 기존 CategoryEnum 이름을 유지하면서 NewsCategoryEnum을 분리해 schema 경고를 해소했다.
- Frontend ESLint/TypeScript, Vitest **4개**, 기존 실제 개발 스택의 Chromium 인증/CSRF E2E **2개** 통과. E2E runner는 호스트 Node 23.7.0이고 Web 서버는 Node 22다. 별도 Node 22 컨테이너에서 Next.js production build 성공. 최초 격리 빌드의 외부 node_modules 심볼릭 링크를 실제 복사로 바꾸어 검증했으며 제품 코드는 수정하지 않았다.
- 개발 DB에 news.0001_initial을 적용했다. DreamNews 정책을 직접 HTTP로 재확인한 뒤 로컬 Source를 명시적으로 등록하고 collect_news를 한 번 실행했다: **created=1 skipped=0 failed=0**. RawItem 1건·pending Candidate 1건·News 0건을 확인했으며 자동 승인/발행하지 않았다.
- 전체 HTML·기사 본문·이미지·신규 라이브러리·Frontend 기능·Compose·기존 도메인 변경 없음. next-env.d.ts의 타입 생성 변경은 복원했다. 원격 GitHub Actions 결과는 확인하지 않았으며 위 결과는 로컬 검증이다.

Phase 8의 수동 수집/API/Admin 완료 조건을 충족한다. 이는 상업적 사용 권한이나 공개 운영 준비 완료를 뜻하지 않는다. Published News 자동 갱신, 변경본 Candidate, revision·재검수, 큐/스케줄러는 구현하지 않았다. 다음 실제 수집은 운영 기본인 하루 한 번 간격을 따른다.
