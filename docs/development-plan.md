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

## Phase 9 — 구현 정책

Phase 8 체크포인트 88573159를 feat/crawler-news에 push하고 feat/async-crawler에서 진행한다. 동기 수집의 출력·종료 코드는 유지한다. collect()는 카운터와 안전한 실패 코드/단계/재시도 가능성을 반환한다. timeout·connection reset/refused·일시적 DNS 실패만 task 수준에서 최대 2회, 60/120초 상한의 full jitter로 재시도한다. HTTP 오류(403/429/5xx 포함), robots/policy/challenge, TLS·영구 DNS, parser, DB/내부 오류, task 시간 제한은 재시도하지 않는다. 하나라도 영구 실패가 섞이면 전체 실행을 자동 재시도하지 않는다.

수집 재실행은 robots/Source/10초 간격을 다시 검사한다. Published News/기존 Candidate를 변경하지 않는다. received/started/retry/succeeded/failed와 broker 확인 후 published를 로그·Celery 이벤트로 관측하며 영구 execution 원장은 없다. task ID는 atomic 안에서는 예약 ID일 뿐이며 실제 발행은 commit 후다. 비활성/미존재 Source는 안전한 실패로 기록한다.

기본 pytest는 broker marker를 건너뛴다. 실제 RabbitMQ 테스트는 RUN_BROKER_TESTS=1과 전용 queue/테스트 DB/별도 prefork Worker로 실행한다. 테스트 Worker의 HTTP transport만 합성 fixture로 대체하고 운영 task와 crawler는 그대로 사용한다. CI에서 실제 외부 사이트를 호출하지 않는다. Admin Run Now, HTTP enqueue API, BatchJob/Schedule/Execution, DB Scheduler, 자동 발행은 Phase 9에서 제외한다.

## 2026-10-10 Phase 9 검증 기록

- Phase 8 체크포인트 **88573159** (`feat: complete manual news crawler and review flow`)을 origin/feat/crawler-news에 push했다. Phase 9 작업 브랜치는 feat/async-crawler이며 Phase 9 변경은 아직 commit/push하지 않았다.
- Celery 5.6.3과 RabbitMQ 4.3.6을 실제 연결했다. RabbitMQ 이미지 digest를 고정하고, RabbitMQ 4.3에서 거부하는 기본 비영속·비독점 제어 큐를 control/event exclusive 설정으로 교체했다. broker의 deprecated 기능을 다시 허용하지 않았다. 수집 큐는 durable classic/persistent를 유지한다.
- 실제 RabbitMQ와 별도 prefork Worker 통합 **11개 통과**. 중복 전달, transient 재시도/소진, 403 비재시도, 저장 rollback, 전체 Worker 종료 후 재전달, 자식 프로세스 종료 후 수동 재실행, JSON 이외 payload 거부, 실제 received/started/retried/succeeded/failed 이벤트를 검증했다. 테스트 큐·프로세스·연결은 종료 후 정리됐다.
- Ruff check/format, Django check, migration drift, OpenAPI validation 통과. 신규 migration·공개 API·Phase 0~8 비즈니스 모델 변경 없음.
- Frontend ESLint/TypeScript, Vitest **4개**, Chromium 인증/CSRF E2E **2개**, 별도 Node 22 컨테이너의 Next.js production build 통과. E2E runner는 기존 호스트 Node 23.7.0을 사용했다. frontend 생성 파일은 복원했으며 변경하지 않았다.
- Compose의 DB/API/Web/RabbitMQ/Worker 모두 healthy, Worker 지정 ping 성공. RabbitMQ 호스트 포트·관리 UI·result backend·자동 승인·revision workflow·scheduler는 추가하지 않았다.
- GitHub Actions에 별도 broker 테스트 단계를 추가했다. 위 결과는 로컬 실행 결과이며 원격 Actions는 실행하지 않았다. 실제 외부 사이트 수집은 이번 검증에서 수행하지 않았다.
- 최종 기본 Backend 전체 **309개 통과, broker 11개 skip**. CELERY_BROKER_URL을 접속 불가능한 주소로 지정해 기본 기능·동기 경로가 broker 연결을 요구하지 않는 것도 확인했다. 별도 실제 broker **11개 통과**와 합쳐 320개 테스트를 검증했다. 정책 미확인 Source 테스트 fixture는 기존 DB 제약에 맞게 비활성 상태로 생성했다.

Phase 9 완료 조건을 충족한다. DB commit/publish 사이의 누락 가능성 및 자식 프로세스 강제 종료의 수동 복구 한계는 유지하며, 영구 실행 이력과 전달 보장 강화는 Phase 10에서 검토한다.

## Phase 10 — 적용 및 운영 정책

Phase 9 체크포인트 623dfe36 (`feat: add celery rabbitmq async crawler worker`)을 origin/feat/async-crawler에 push하고 feat/batch-platform에서 구현한다. 기존 news.collect 큐의 ready/unacked와 Worker active/reserved/scheduled가 비어 있는 것을 확인한 뒤 Worker를 중지했다.

적용 순서: 기존 비동기 접수 중지 및 큐 drain → 새 이미지 → migrate → configure_batch_jobs → Batch Worker 시작. 초기 Job은 비활성이며 Schedule은 생성하지 않는다. `/batch`에서 staff에게 view_batch와 필요한 run_batch/manage_batch를 부여하고 Source/활성을 설정한다. 운영 Cron은 화면에서 등록한다. 기본 예시는 입력 편의일 뿐 저장/활성화 전 실행되지 않는다.

News 실행은 기존 Source 활성/robots/요청 간격/metadata 불변 정책을 재검증한다. transient만 같은 원장에서 최대 2회 자동 retry하며 동기 명령은 자동 retry하지 않는다. `collect_news`와 `enqueue_news_collection` 모두 설정된 활성 News Job/Source를 필요로 한다. 동기 명령은 broker 없이 원장을 남기고 기존 카운터/실패 종료 코드를 유지한다. enqueue 명령은 실행 접수 ID와 task ID를 출력하며 수집 성공을 뜻하지 않는다.

Scheduler misfire는 유효 기간의 가장 최근 회차 하나로 합친다. busy 상태에는 due를 보존하고 실행 종료 후 합친다. 일정 수정/재활성화는 미래 회차부터, 이미 끝난 기간은 보정 실행하지 않는다. API/Worker는 전체 업무를 atomic으로 묶지 않는다. 토큰 정리는 고정 cutoff에서 만료 OutstandingToken을 500개씩 먼저 잠그며 잠긴 행을 건너뛴다. 각 묶음의 blacklist 삭제는 같은 트랜잭션이다.

RUNNING의 hard limit+120초 경과는 경고일 뿐이다. Worker의 실제 종료를 확인하고 실패 확정한 다음 Retry한다. 기존 업무의 부분 성공 가능성이 있으므로 뉴스 중복 제약·토큰 정리 재실행 안전성이 필요하다. 전달 중복/최종 원장 저장 실패는 자동으로 성공 처리하지 않는다.

검증은 실제 PostgreSQL 및 별도 RabbitMQ/prefork Worker, 합성 HTTP fixture를 사용한다. 자동 테스트는 실제 출처에 접근하지 않는다. 원격 CI 실행 여부와 로컬 결과는 별도로 기록한다.

## 2026-10-11 Phase 10 검증 결과

- 최종 Backend 기본 회귀 **342개 통과**, broker 그룹 16개는 별도 실행으로 분리했다. 실제 PostgreSQL/PostGIS에서 접수/claim/Retry 경합, Scheduler 잠금·misfire, DB 제약, rollback, migration upgrade 시 기존 News·Collection 보존을 확인했다.
- 실제 RabbitMQ와 별도 prefork Worker **16개 통과**. API 접수 후 broker 장애 복구, 중복 메시지, 발행 확인 후 DB 기록 유실, retry 발행 유실, 전체/자식 Worker 종료, 최종 원장 기록 실패, JSON 제한 및 토큰 정리 실행을 검증했다. 외부 사이트 대신 고정 HTTP fixture를 사용했다.
- 토큰 정리는 Refresh/Logout이 실제 OutstandingToken 잠금을 보유할 때 건너뛰고, blacklist 관계와 함께 원자적으로 삭제되는 것을 검증했다. 기존 인증 정책과 news 검수/발행 불변 정책은 유지한다.
- Worker가 publisher보다 먼저 완료해도 발행 확인 시각을 기록하며 완료 상태/다음 시도 시각을 덮어쓰지 않도록 경합 회귀 테스트를 추가했다.
- Ruff check/format, Django check, migration drift, OpenAPI validation과 실제 응답 계약 테스트 통과. Backend 이미지도 새 lockfile로 빌드했다.
- Frontend ESLint/TypeScript, Vitest **9개**, 실제 Chromium E2E **4개** 통과. E2E는 인증/CSRF와 Batch 운영자 RSC·권한별 버튼·실제 잘못된 Cron 거부를 포함한다. 임시 운영자와 토큰은 테스트 종료 시 제거한다. Run Now 응답 유실/중복 클릭의 동일 키 유지, 스케줄 오류와 stale 확인 UI는 단위 테스트로 검증했다.
- 별도 Node 22 컨테이너의 Next.js production build 통과. 호스트 E2E runner는 기존 Node 23.7.0이다. 생성된 next-env 변경은 복원했다.
- 로컬 DB에 batch.0001_initial을 적용하고 명시적인 등록 명령으로 **비활성 Job 2개, Schedule 0개, Execution 0개**를 확인했다. API/Web/DB/RabbitMQ/Worker/Scheduler healthcheck 통과. 실제 News 수집이나 토큰 정리 Job을 로컬 운영 데이터에 실행하지 않았다.
- CI에 초기 Job 등록·Scheduler 단일 tick 및 Scheduler profile 기동을 추가했다. 위 결과는 로컬 검증이며 원격 GitHub Actions는 실행하지 않았다.
- 추적 파일에서 .env·개인 경로·개인키/토큰 패턴과 불필요한 생성물을 확인하지 못했다. Phase 10 변경은 feat/batch-platform에 **미커밋**으로 남긴다.

완료 범위는 DB 일정/원장/전달 복구와 최소 운영 화면이다. 자동 장애 판정, exactly-once 업무 수행, DST 시간대, 다중 Schedule/Source 병렬 실행, 실행 이력 자동 삭제는 구현하지 않았다. 동기 수집 명령에는 Celery 프로세스 시간 제한이 적용되지 않으며 기존 HTTP timeout과 원장/실행 중복 제한을 사용한다. 주기적 일정과 발행 유실 복구를 사용하려면 scheduler profile을 실행해야 한다.


## 2026-10-17 Phase 11 — Redis 필요성 측정 및 판단

Phase 10 commit `f9363d26`의 [원격 GitHub Actions](https://github.com/juniel1299/ChiikawaGo/actions/runs/38093395798) 성공을 확인하고 `perf/redis-evaluation`에서 측정했다. Phase 11은 Redis 구현 단계가 아니라 필요성 측정 단계로 정의한다.

결론은 **C: Redis adoption deferred after measurement**다. [측정 보고서](../benchmarks/redis-evaluation/REPORT.md), [전체 결과표](../benchmarks/redis-evaluation/RESULTS.md), [재현 방법](../benchmarks/redis-evaluation/README.md)에 seed·데이터 규모·부하 조건·raw 결과·실행계획을 기록했다. runserver/Apple Silicon/에뮬레이션 PostGIS의 상대 비교 결과이며 운영 capacity 또는 확정 SLO로 사용하지 않는다.

10x 밀집 Nearby는 3 req/s에서 오류 없이 처리했지만 5 req/s에서 CPU 포화와 64 MiB 공유 메모리 제약이 나타났다. 넓은 반경은 baseline → JIT off → 원복의 단일 변경 실험으로 p95 약 771 → 316 → 812ms를 확인했다. Redis 이전에 운영 서버/native DB·공유 메모리·쿼리/count 비용을 검증할 근거다. 로그인 burst 270건은 모두 401이었고 제한 응답은 없으므로 공개 운영 전 rate limiting 정책 검토는 별도로 필요하다.

Redis dependency, Compose 서비스, cache backend를 추가하지 않았다. Batch locking/PostgreSQL, Celery/RabbitMQ, BatchExecution, JWT blacklist와 Django session을 유지한다. JIT는 기본값으로 원복했다. 서비스 코드·API 계약·기존 migration 변경은 없다. 운영 환경 검증, 실제 재사용률·최신성 요구, proxy/gateway 및 필요 시 분산 limiter 비교는 후속 고려사항이다.


Phase 11 최종 승인: **C — Redis adoption deferred after measurement**. Nearby의 PostGIS/count/DB 자원 비용, JIT 단일 변경의 영향, 로컬 shared-memory 오류를 Redis 필요성으로 혼동하지 않는다. Character/News 캐시의 필수성은 확인되지 않았으며 synthetic 재사용률은 실제 사용자 hit rate가 아니다. Rate limiting은 별도의 abuse protection 요구로 유지한다.

체크포인트에는 benchmark 스크립트·README/REPORT/RESULTS와 소규모 집계·환경·검증 기록만 포함한다. 요청별 raw, 상세 실행계획, pilot, 생성 차트·raw 해시 manifest는 로컬에 보존하고 Git에서 제외한다. fresh checkout의 집계만으로 과거 raw를 재검증할 수는 없으며 재현 절차로 새 raw를 생성한다. Phase 12 Flutter/GPS/Map은 다음 설계 단계이며 이 체크포인트에서 구현하지 않는다.


## Phase 12 — Flutter 구현 / 검증 중

`feat/flutter-mvp`에서 Android/iOS용 `mobile/`을 추가한다. Flutter stable 3.47.7 / Dart 3.13.5와 pubspec.lock을 고정하고 flutter_riverpod(코드 생성 없음), Dio, flutter_secure_storage, geolocator, google_maps_flutter를 사용한다. 인증·위치·Nearby·지도·Encounter·Capture·Collection만 구현한다.

기존 Backend API와 모델은 변경하지 않는다. Access는 메모리, Refresh는 secure storage, 동시 갱신은 단일 실행이며 원 요청 retry는 한 번이다. Logout과 refresh/login을 직렬화하고 계정별 화면 상태를 제거한다. 위치는 foreground 단발 조회이며 권한 거부/제한·대략적 위치·서비스 중단·timeout·복귀를 처리한다. Nearby는 명시적 조회, 고정 좌표 pagination 및 늦은 응답 무시를 적용한다. Encounter 직전에 새 GPS를 확보하고 Capture는 위치 없이 같은 ID로 재시도한다.

[모바일 실행·검증 안내](../mobile/README.md)에 환경, 키 제한, 자동 테스트와 실기기 acceptance를 구분한다. **실기기 및 iOS 빌드 미검증이므로 Phase 12 전체 완료로 표시하지 않는다.** Redis·background location·Push·Community/News/Batch UI·이미지 인프라·3D/AR/Unity는 추가하지 않는다. Phase 11 성능 결론은 유지하고 추가 최적화하지 않는다. 사용자 요청에 따라 검증 결과를 먼저 보고하며 commit/push하지 않는다.


### 2026-10-17 Phase 12 로컬 검증

- Flutter stable 3.47.7 / Dart 3.13.5, Android compile/target SDK 36, min SDK 24, Java 17.0.13, Gradle 9.3.1, NDK 28.2.13676358. Doctor의 Flutter/Android 항목 통과. Xcode는 전체 설치가 없어 실패이며 iOS 빌드 미검증.
- Unit 35개 + Widget 3개 통과, 정적 분석·format 통과, Android debug APK 빌드 통과. 지도 키 없이 목록 대체 UI로 컴파일했다.
- 별도 실제 Django/PostGIS에서 Flutter 컨트롤러의 로그인 → Nearby → Encounter → 반복 Capture → Collection → Refresh 복원 → 로그아웃 통합 테스트 1개 통과. GPS·보안 저장소는 대역이며 네이티브 실기기 검증을 대신하지 않는다. 테스트 전용 DB/컨테이너는 정리했다.
- Android 실기기 미연결, iOS 실기기/전체 Xcode 없음, Google Maps 키 미제공으로 실제 지도·플랫폼 보안 저장소·위치 권한 UX는 미검증. 실제 API key 제한과 배포 signing도 아직 적용·검증되지 않았다.
- 모바일 CI workflow를 추가했지만 commit/push 및 원격 실행은 하지 않았다. Backend/Frontend/기존 Compose·API·모델 변경 없음. 실기기 acceptance 통과 전 Phase 12 전체 완료로 확정하지 않는다.

### 2026-10-20 Phase 12 자동 검증 재실행

- 고정 Flutter 3.47.7 / Dart 3.13.5, Android SDK 36 / Java 17.0.13을 재확인했다. 의존성 lock 검증, analyzer, 전체 Dart format, Unit 35개 + Widget 3개, Android debug APK 빌드가 통과했다.
- 별도 Django/PostGIS HTTP 통합 테스트 1개가 통과했고 테스트 컨테이너를 정리했다. 일반 테스트의 해당 1개 skip은 별도 실행을 위한 의도된 설정이다.
- 전체 Xcode 미설치로 iOS build/Simulator를 실행할 수 없고 Android 실기기도 미연결이다. 사용자는 자동 검증 후 실기기를 미검증으로 남기도록 선택했다. Android emulator도 이번에 실행하지 않았다.
- 지도 키 파일이 없어 실제 Google Maps와 플랫폼 키 제한은 미검증이다. 실제 GPS/권한 UX/Keychain·secure storage/플랫폼 전체 흐름도 실기기 검증을 대신하는 것으로 간주하지 않는다.
- Gradle의 `mobile/android/build/` 보고서가 Git 후보에 들어오는 문제를 ignore 항목으로 수정했다. 앱 기능·Backend·패키지 변경은 없다. 민감정보 패턴과 생성물 점검 결과 및 한계는 [모바일 검증 기록](../mobile/README.md)에 남겼다.
- 상태: **IMPLEMENTATION COMPLETE / DEVICE VALIDATION PENDING**. commit/push 및 원격 CI 실행은 하지 않았다.
