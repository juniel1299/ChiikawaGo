# Phase 11 — Redis 필요성 측정 및 판단

## 범위와 결과 읽는 방법

이 보고서는 `f9363d26`의 서비스 코드를 바꾸지 않은 로컬 비교 시험이다. Redis dependency/service/backend를 추가하지 않았다. 실제 crawler·Worker·Scheduler는 실행하지 않았다. 최종 수치는 [RESULTS.md](RESULTS.md), 반복별 범위와 자원 지표는 [summary.csv](results/summary.csv), 개별 요청 `results/*-requests.jsonl`과 상세 실행계획 `results/*-diagnostics.json`은 로컬에만 보존하고 Git에서 제외한다. 생성 차트도 로컬 산출물이며 `plot.py`로 재생성한다. 차트는 측정 지점만 연결하며 지점 사이의 capacity를 추정하지 않는다.

**Apple M4 Pro + Docker Desktop arm64 + amd64 에뮬레이션 PostGIS + Django runserver 결과이며 운영 capacity가 아니다.** 현재 실제 수요 예측, 확정 SLO, 운영용 WSGI/native Linux 결과가 없으므로 Redis 필요성을 단정하는 근거로 단일 latency 숫자를 사용하지 않는다. p95 200ms는 비교선일 뿐이다.

## 재현 조건

- 전용 `chii-perf` DB/API, 각각 2 CPU/2 GiB. Docker VM 12 CPU, 약 7.65 GiB. 호스트 부하 생성기는 같은 머신에서 실행했다.
- Seed 20261016, Spot/Character/Variant/Raw/Candidate/News UUID5, 고정 합성 공간 분포와 발표 시각. 계정/Source ID 및 자동 생성 감사 시각은 환경별이며 검색·정렬 조건에는 사용하지 않는다.
- 1x: Spot 10,000 / Character 100 / Variant 500 / 발행 News 10,000. 10x는 각각 10배다. 실제 예상 규모로 확정한 값이 아니다.
- 전체 Spot의 50%를 작은 합성 밀집 구역에 배치했다. 10x에서는 같은 면적에 밀도도 10배가 된다. 특히 넓은 반경 결과는 의도적 스트레스 조건이며 현실 분포를 대변하지 않는다.
- 본 matrix: 8 시나리오 × 동시 사용자 1/5 × 3회 × 두 규모. 2초 이상 워밍업 후 진행 요청 종료, 8초 측정 요청 발행, 완료까지 drain. 운영 장기 안정성 시험이 아니다.
- 추가 동시성: 10x Character/News 10·25명, 밀집 Nearby 2·10명, 각 3회 동일 시간.
- 고정 도착률: 10x 밀집 Nearby 1/3/5 req/s, 3초 워밍업 후 30초, 각 3회. 예정 시각부터 완료까지 측정해 큐 대기 지연을 포함한다. 최대 50 실행 스레드이며 초과 대기도 latency에 포함된다.
- 로그인: 합성 계정의 잘못된 비밀번호, 동시 1/5/10, 각 30 요청 × 3회. 테스트별 랜덤 비밀번호는 메모리에만 유지한다.
- 짧은 반복에서 N<100인 p99는 최대값에 가까운 관측치일 뿐 안정적인 tail 추정이 아니다. 원본 N과 반복별 변동을 함께 읽는다.
- 첫 1x와 재개 후 10x는 별도 세션이다. 동일 이미지/자원 설정은 확인했지만 호스트 열·부하·에뮬레이션 상태를 통제하지 않았다. 특히 초기 1x News 변동을 10x와 직접 비교해 규모 증가 효과를 주장하지 않는다.

## DB / PostGIS 원인

10x 독립 진단에서 밀집 Nearby 전체 중앙값은 약 262ms, 인증 35ms(연결 약 25ms 포함), count SQL 122ms, 목록 SQL 100ms, SQL을 제외한 ListSerializer 약 0.45ms였다. 이 타이머들은 일부 중첩하며, 부하 HTTP percentile에 더할 수 없다. 순수 PostGIS 함수 CPU만 분리한 결과도 아니다.

warm `EXPLAIN (ANALYZE, BUFFERS)`에서 밀집 count/목록은 약 94/93ms, 넓은 반경은 약 276/152ms였다. GiST bitmap index가 사용됐다. 밀집 목록은 약 38,378개, 넓은 반경은 약 55,892개 활성 후보의 거리·필터 작업이 필요하다. 인덱스가 없어서 전체가 느린 상황은 아니다. count와 정렬의 후보 처리 비용, 병렬 쿼리 작업자 생성, cold connection/function 초기화 비용을 구분해야 한다.

News 첫 페이지 SQL은 warm 약 0.11ms이며 `news_latest`를 사용했다. 전체 count는 약 38ms이고 승인 Candidate와의 join/전체 집계가 필요했다. category 목록은 `news_category_latest`를 사용했으며 count 약 28ms, 목록 약 0.11ms였다. 단순히 인덱스를 하나 더 추가하는 것이 첫 해결책은 아니다.

DB CPU는 동시 부하에서 설정된 2 CPU 한도 부근까지 도달했다. 연결 수는 `pg_stat_activity`의 해당 DB 행 수여서 parallel worker도 포함한다. 관측한 lock wait는 0이지만, 약 3초 간격 표본이므로 순간 잠금이 전혀 없었다는 뜻은 아니다. Batch/쓰기 경합의 성능을 이 읽기 시험으로 증명하지 않는다.

## Redis 없는 단일 변경 실험

실행계획에서 넓은 반경의 JIT 비용을 확인한 뒤 **전용 DB의 `jit` 기본값만 off**로 변경했다. 데이터·SQL·인덱스·API·자원 한도는 유지했다. 같은 조건으로 세 번 측정하고 기본값을 reset해 원복 시험도 했다.

10x 넓은 반경, 동시 1명:

- baseline: p95 771ms, 1.42 req/s.
- JIT off: p95 316ms, 3.61 req/s.
- 원복: p95 812ms, 1.41 req/s.

동시 5명도 처리량 약 1.04 → 2.24 → 1.07 req/s였다. JIT가 사용되지 않던 밀집 1km와 News에는 같은 개선이 없었다. 따라서 캐시 없이 특정 실행계획 비용을 줄일 수 있음을 확인했다. **운영 DB 전역 JIT를 끄라는 결론은 아니다.** native 환경에서 해당 쿼리와 다른 업무에 대한 효과를 다시 검증해야 한다.

연결 재사용은 실행하지 않았다. Django 공식 문서는 runserver 스레드 특성이 persistent connection 효과를 무효화한다고 설명한다. 운영용 서버/연결 수명·pool 검토는 다음 성능 검증 후보이며 이번 수치로 효과를 주장하지 않는다.

## 반복 조회와 캐시 대안

고정 위치·동일 page/filter 시나리오는 동일 키 재사용이 높고, 각 요청의 위치가 바뀌는 시나리오는 거의 0이다. 이것은 합성 workload가 만든 상·하한이며 실제 사용자 hit ratio가 아니다. 8초 시험의 10/30/60초 창은 최적 TTL을 구분할 수 없다. 실제 이동/탐색 빈도와 허용 최신성을 확보하기 전 Redis key/TTL을 확정하지 않는다.

- Nearby: 반복 요청 합치기, 이동 거리/조회 주기 조절을 먼저 검토한다. 좌표 반올림으로 최종 응답을 공유하면 거리·경계·정렬이 달라질 수 있으므로 이번에는 적용하지 않았다.
- 공개 목록: 현재 `no-store` 계약이다. Cache-Control/Next.js revalidation/CDN은 공개 데이터 최신성·무효화 정책을 합의한 뒤 비교한다. 이번에 적용하거나 효과를 측정하지 않았다.
- ETag: body 계산 후 해시만 생성하면 전송량만 줄고 count/SQL 비용은 남는다. origin DB 절감과 네트워크 절감을 혼동하지 않는다.
- count 비용: count 없는 pagination/cursor는 API 계약 변경이므로 이번에 적용하지 않았다. 승인 정책을 깨는 join 제거도 하지 않았다.

## Rate limiting과 유지할 구조

성능과 별개로 공개 운영 전 로그인 abuse/burst 제한이 필요하다. 단일/소수 인스턴스에서는 앞단 reverse proxy/API gateway와 계정별 정책을 먼저 검토할 수 있다. PostgreSQL 제한은 낮은 빈도에서 후보지만 카운터 쓰기 경합을 별도로 검증해야 한다. Redis는 여러 인스턴스의 공통/원자적 제한이 요구되고 앞단 정책으로 부족할 때 재검토한다. 이번에는 이 세 limiter를 구현하거나 성능 비교하지 않았다.

DRF 기본 throttle에 Redis cache를 연결하는 것만으로 엄격한 동시 제한이나 brute-force 보호가 보장되지는 않는다. 실제 사용자 오차 차단, 공유 IP, 신뢰하는 proxy 헤더, 계정/IP별 정책과 장애 동작을 먼저 정의해야 한다.

Batch locking은 PostgreSQL, broker는 RabbitMQ, 실행 상태는 BatchExecution, JWT blacklist와 Django session은 현재 저장 구조를 유지한다.

## 근거 문서

- [Django persistent connections와 runserver 주의사항](https://docs.djangoproject.com/en/5.2/ref/databases/#persistent-connections)
- [PostgreSQL JIT 판단과 비용](https://www.postgresql.org/docs/17/jit-decision.html)
- [DRF throttle의 동시성·보안 한계](https://www.django-rest-framework.org/api-guide/throttling/)


## 최종 포화 관측과 오류 해석

10x 밀집 Nearby 고정 도착률에서 1/3 req/s는 각각 90/270건 모두 200이었다. 3 req/s p95는 332ms였다. 5 req/s는 450건 중 200 72건, HTTP 500 66건, client transport/timeout 312건으로 성공 처리량 중앙값은 0.63 req/s였다. 실패율은 84%다. 이 구간의 약 10초 p50/p95/p99는 client timeout으로 잘린 관측치이며 실제 성공 응답의 지연 상한이 아니다.

동일 로컬 구성의 안정 구간과 붕괴 구간은 관측한 도착률 **3~5 req/s 사이**다. 정확한 임계값은 측정하지 않았다. closed-loop 밀집 Nearby는 동시 1/2/5/10명에서 약 3.63/4.13/2.45/2.51 req/s로 2명 이후 처리량 증가가 멈췄다. Character는 동시 1/5/10/25명에서 25.45/41.66/26.24/24.20 req/s, News는 11.83/11.86/6.66/4.98 req/s였다. 별도 세션의 추가 동시성 결과이므로 이 지점들을 정밀한 용량 곡선으로 해석하지 않는다.

**고부하 오류에는 측정 환경의 공유 메모리 제한이 개입했다.** 전용 PostgreSQL 컨테이너의 `/dev/shm`은 64 MiB였다. 전체 컨테이너 수명 로그에서 `could not resize shared memory segment`와 `No space left on device`가 각각 395회, API OperationalError가 396회 관측됐다. 이 집계는 워밍업·제외 pilot까지 포함하며 각 500과 일대일 매핑한 수치가 아니다. 원문 SQL·파라미터·로그는 저장하지 않고 고정 오류 패턴의 건수만 `overload-diagnosis.json`에 남겼다. too-many-clients/OOM 패턴은 관측되지 않았다.

News 추가 동시성 10/25명에서는 HTTP 500이 각각 73/140건 발생했다. DB 병렬 연산의 공유 메모리 부족은 캐시가 해결해야 할 고유 문제라고 볼 수 없다. CPU도 2코어 한도 부근이었으므로 **다음 실험은 적절한 shared-memory 크기와 운영 서버에서 동일 조건 재측정**이다. 이번에는 JIT 외 설정을 더 바꾸거나 여러 개선을 합치지 않았다. 따라서 공유 메모리 확장의 효과를 측정한 것으로 주장하지 않는다.

5 req/s에서 pg_stat_activity 최대 79행, 표본 lock wait 0이었다. parallel worker가 포함된 값이며 최대 79개의 HTTP 사용자/클라이언트 DB connection을 뜻하지 않는다. 부하 생성기·API·DB가 동일 호스트의 자원을 공유하는 제약도 남는다.

## 로그인 burst와 재사용률

잘못된 비밀번호 270개 요청은 모두 401, 429는 0이었다. 동시 1/5/10명에서 처리량 중앙값은 약 5.04/10.77/7.66 req/s였다. 동시 10명에서는 반복별 p95가 약 1.49~1.71초로 증가했다. 애플리케이션에 앞단 제한이 없는 이 시험에서는 비밀번호 검증 작업이 계속 실행됐다. 이는 공개 운영 전 rate limiting 정책이 필요하다는 근거이며, Redis가 유일한 구현 수단이라는 근거는 아니다. 실제 공격 규모나 안전한 로그인 허용량은 이 소규모 시험으로 정하지 않는다.

10x baseline의 합성 동일 키 요청에 대한 10초 재사용 가능 비율은 약 90.0~99.7%, 이동 좌표 시나리오는 0%였다. 공개 Character/News 고정 페이지는 약 98.9~99.7%였다. 실제 캐시를 구현하지 않았으며 인증 주체별 응답 공유, 무효화, 실패 응답 저장을 검증한 hit ratio가 아니다.

## 판단: C — 현재 Redis 도입 보류

Phase 11은 **Redis adoption deferred after measurement**로 완료한다. 완료는 로컬 상대 비교와 도입 판단의 완료를 의미하며 운영 성능 목표 달성이나 공개 배포 승인을 의미하지 않는다.

- Nearby는 GiST를 사용하지만 고밀도 후보 처리/count/거리 정렬 비용이 크다. JIT 단일 변경의 가역적 개선을 확인했고, 공유 메모리와 운영 서버 조건의 재검증이 Redis보다 먼저다.
- 공개 목록은 동일 요청 재사용 잠재력이 있지만 실제 트래픽 재사용률·허용 최신성·최종 SLO가 없다. 기존 인덱스, count 비용, HTTP/Next/CDN 정책을 먼저 평가한다.
- 로그인/공개 API의 abuse 방어 요구는 별도로 남긴다. 초기 앞단 proxy/gateway 정책으로 충분한지 확인하고, 다중 인스턴스에서 공통 원자적 제한이 필수이고 기존 앞단으로 충족하지 못할 때 Redis limiter를 다시 설계한다.
- Batch 잠금, Celery broker, 실행 원장, JWT blacklist, Django session은 기존 구조를 유지한다.

Redis 재검토 기준은 운영과 가까운 환경에서 합의한 latency/error 목표를 지속적으로 위반하고, DB/쿼리/요청 빈도 개선 후에도 병목이 남으며, 실제 동일 키 재사용과 허용 staleness로 기대 절감량을 설명할 수 있는 경우다. p95 200ms만 넘었다는 이유로 도입하지 않는다. 재검토 시 key/TTL/invalidation/fallback/consistency와 회귀 테스트를 먼저 설계한다.

## 결과 검증과 정리

본 측정 147회·13,343 요청과 로그인 9회·270 요청의 raw/요약 일치 여부, 반복 키 중복 여부, 성공 건수와 p95 계산을 검증했다. 오류를 제거해 성능을 좋게 보이게 하지 않았으며 제외 pilot은 별도 파일로 보존했다. 집계 검증 기록 `validation.json`은 커밋에 포함하고, raw 파일의 `manifest.json`은 로컬에만 보존한다. 측정 스크립트의 Ruff 검사/format 및 Python 구문 검증을 통과했다. 서비스 코드·의존성·migration은 변경하지 않아 전체 기능 테스트를 다시 실행하지 않았다. 이전 Phase 10 원격 CI 성공과 이번 측정 검증을 구분한다.

JIT는 기본 on으로 원복했다. 측정용 컨테이너만 중지하고 합성 DB volume은 재현을 위해 유지한다. 사용자 승인에 따라 재현 스크립트·문서·소규모 집계만 Phase 11 체크포인트에 포함한다. 서비스 코드와 Redis 설정은 추가하지 않는다.
