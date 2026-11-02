# AdLoom TASKS

에이전트 루프가 읽고 갱신하는 태스크 상태표입니다. 내용·AC의 근거는 `SPEC.md` §4~§8입니다.

상태 값: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED` · `LIVE-OK`(T10~T13 live 검증을 사람이 승인한 표시).

**규칙:** 선행이 모두 `DONE`인 첫 `TODO`만 고릅니다. 목표일은 소프트 마감입니다. 상태 열과 메모 열만 수정하고 나머지 열은 바꾸지 않습니다 (바꿀 필요가 있으면 `SPEC_CHANGES.md`에 제안).

T00~T09는 mock만으로 끝나며 킥오프(10/26) 전에 돌릴 수 있는 범위입니다. H1~H4는 사람 게이트입니다 (`AGENTS.md`).

| ID | 상태 | 내용 | 선행 | 파일 | 담당 AC | 목표일 | 메모 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T00 | DONE | 스캐폴드: pyproject, Makefile(`make check`), ruff·mypy·pytest 설정, `AGENTS.md`, ffmpeg로 1920×1080 10초 합성 샘플 영상(움직이는 도형) 생성 스크립트 | 없음 | `pyproject.toml`, `Makefile`, `tests/fixtures/make_sample.sh` | AC-19 스캔 테스트 골격 | 10/24 | 10/27 사용자 구현 재개 지시로 진행했다. 실패 테스트 확인 후 합성 생성기를 구현했으며 make check 53개 통과, 실제 샘플 H.264·1920×1080·300프레임·10초를 확인했다. 비밀 패턴 스캔 통과. |
| T01 | DONE | `schemas.py`, `config.py`: 모델·상수, LIVE 게이트, Contributor ID 거부 | T00 | `schemas.py`, `config.py` | AC-01(스키마), AC-18, AC-21 | 10/24 | 10/27 기존 스키마를 재사용하고 설정·Standard 제한·명시 live 요청 거부를 구현했다. 실패 테스트 후 make check 55개 및 설정 로드 smoke 통과. H2/H3 승인 전 live는 E_API_AUTH로 종료하며 mock으로 전환하지 않는다. |
| T02 | DONE | `jobs.py`: Job 저장, 상태 머신 전이 규칙(§3), `job.json` 원자적 쓰기 | T01 | `jobs.py` | §3 전이 테스트 | 10/24 | 10/27 immutable snapshot·atomic head·digest·stale commit 거부·실행 lock·실패 재개를 구현했다. 전체 전이표 81조합 포함 make check 138개 및 실제 저장/실패/재개 smoke 통과. |
| T03 | DONE | `crop.py` 순수 함수와 박스 보간 | T01 | `crop.py` | AC-06, 07, 09 | 10/24 | 10/27 보간·고정 비율·6% 여백·평활·24px 이동 상한·중앙 대체를 구현했다. 불가능한 포함은 clipped/safe-area 표시로 남긴다. make check 143개 및 all-null 300프레임 smoke 통과. |
| T04 | DONE | `policy.py` 규칙 기반 점검과 순화 (규칙 표는 `policy_rules.yaml`) | T01 | `policy.py`, `policy_rules.yaml` | AC-05 | 10/25 | 10/27 보장·의학적 단정 문구 탐지와 순화 제안을 구현했다. make check 144개와 100% 보장→순화본 재검사 smoke 통과. Meta 정책 승인이나 사실 검증을 보장하지 않는다. |
| T05 | DONE | 어댑터 Protocol 5개 + Mock 5종 + 팩토리 | T01 | `adapters/base.py`, `adapters/mock_*.py` | AC-21 | 10/25 | 10/27 Protocol 5개·digest fixture·합성 추적·PNG·전사 fixture·PAUSED publisher를 구현했다. make check 147개와 샘플 이해/300프레임 추적/PNG smoke 통과. unknown fixture와 live 요청은 명시 거부한다. |
| T06 | DONE | 스테이지: 입력·이해·추적·보강 | T02, T03, T04, T05 | `stages/` | AC-01, 02, 03, 04, 08, 10 | 10/25 | 10/27 정규화·음성 설명 전사·1회 schema repair·정책 재검사·추적/중앙 대체·Image 실패 대체를 구현했다. make check 151개와 실제 입력→보강 파일 처리 smoke 통과. live 모델 품질은 미검증이다. |
| T07 | DONE | `render.py` + 조립 스테이지: ffmpeg 렌더, 훅·자막·엔드카드 오버레이, 폰트 | T03 | `render.py`, `stages/assemble.py` | AC-11, 12, 13, 14 | 10/25 | 10/27 5080 서버에서 6종 렌더·H.264/yuv420p/AAC·길이·반복 frame hash·훅 제거를 검증했다. make check 154개 통과. 시간축/자막 매핑·폰트/소스 hash·허용 소스 검증 포함. 결정론은 동일 build 범위다. |
| T08 | DONE | Marketing Mock과 게시 스테이지, 멱등성 | T02, T05 | `stages/publish.py` | AC-15, 16, 17 | 10/25 | 10/27 승인 digest·실제 파일 hash·최종 정책 재검사·operation journal·부분 재개를 구현했다. make check 159개, 실제 저장 smoke에서 9요청·광고2개·중복0 확인. PAUSED는 campaign/adset/ad에 강제하며 결과 불명은 재전송하지 않는다. |
| T09 | DONE | `cli.py`와 파이프라인 오케스트레이터, mock E2E | T06, T07, T08 | `cli.py`, `pipeline.py` | AC-20 | 10/25 | 10/27 run/list/inspect/resume/edit/approve/publish를 연결했다. 5080 make check 160개와 실제 CLI AWAITING_APPROVAL→APPROVED→PUBLISHED_PAUSED·6종 파일 smoke 통과. 편집 시 revision 증가·승인 무효화·재렌더/재승인 회귀 포함. |
| T10 | BLOCKED | Live Spark 어댑터 (**H2**) | T09 | `adapters/spark.py` | live 테스트, AC-03·04를 Live 응답 fixture로 재검증 | 10/27 | 11/2 코드와 httpx MockTransport 테스트를 b709e68에 커밋했다(5080 make check 217개 통과). `get_adapters`는 mock만 반환하고 `ADLOOM_LIVE=1`은 계속 E_API_AUTH로 거부한다. 실제 응답 검증은 H2(키 발급·비용 한도·전송/보관 동의·실행 승인) 대기. 미확인 가정은 `docs/api_notes/spark.md`. |
| T11 | BLOCKED | Live SAM 어댑터, 마스크 → 박스 변환 (**H2**) | T09 | `adapters/sam.py` | live 테스트, AC-06 재검증 | 10/28 | 11/2 스트림 파싱·박스 변환·객체 선택 코드와 문서 예시 페이로드 테스트를 b709e68에 커밋했다. 0건 응답 형식·오류 이벤트 페이로드는 미확인(`docs/api_notes/sam.md`). live 검증은 H2 대기. |
| T12 | BLOCKED | Live Image·Voice 어댑터 (**H2**) | T09 | `adapters/image.py`, `voice.py` | live 테스트, AC-10 | 10/29 | 11/2 코드와 mock 전송 테스트를 b709e68에 커밋했다. 반환 이미지 크기·ENDPOINTING 지원·한국어 정확도는 미확인. 업로드 파일 삭제(`cleanup`)는 아직 파이프라인에 연결하지 않았고 보관 정책 결정(H2)에 따른다. |
| T13 | BLOCKED | Live Marketing 어댑터 (**H3**) | T09 | `adapters/marketing.py` | live 테스트, AC-16·17 재검증 | 11/2 | H3 실제 계정·권한·목표·CTA/destination·Graph 버전·예산·일정 및 실행 승인 대기. |
| T14 | DONE | 웹 승인 화면: 변형 6개 미리보기, `degraded`·정책 플래그 표시, 승인 버튼 → `approval.json` | T09 | `web/` | AC-15 (웹 경로) + 수동 확인 | 10/30 | 11/2 Figma 설계(https://www.figma.com/design/9T5bAydiWPfdhFWNpoiZK5) 기준으로 FastAPI + 단일 HTML 로컬 웹을 구현했다. 작업 목록·업로드·6종 검토·승인(channel web, digest 대조)·문구 편집·PAUSED mock 게시·게시 기록·설정 화면. `tests/test_web.py`에서 미승인 게시 409·adapter 미호출(AC-15 웹 경로), stale digest 거부, 교차 사이트 쓰기 403, 미디어 경로 제한을 검사한다. 실제 Chromium에서 업로드→검토→승인→게시와 정책 차단 표시, 390px 폭을 확인했다. worker·session·장면/객체 편집은 미구현. |
| T15 | TODO | 실영상 LIVE 리허설: 실제 점포 영상 1~2건 전 과정, 실패 기록 | T10~T13, T14 | `docs/rehearsal.md` | 완료 정의(§1) | 11/3 | |
| T16 | BLOCKED | 제출물: README, 데모 대본·촬영 체크리스트 (**H1, H4**) | T15 | `README.md`, `docs/demo.md` | — | 11/4 | 10/27 Official Rules 원문을 확인했다. 원본 9절의 미공개 기록과 달라 원본 7절에 따라 SC-016을 제안했다. H1 참가자 수락·사전 자체 코드 조건, H4 로그인 뒤 제출 형식 확인 및 T15 완료를 기다린다. |

## 사람 게이트

| 게이트 | 내용 | 막히는 태스크 | 상태 |
| --- | --- | --- | --- |
| H1 | Official Rules 확인(10/26 전 공개): 허용 모델, 기존 코드 사용, 제출 형식 | T16 | 원문 확인(10/27, SC-016). 참가 승인·자격·약관 수락, 사전 자체 코드 조건, 로그인 뒤 제출 형식은 대기한다. |
| H2 | API 키 발급·환경변수 설정, 한국에서 호출 가능한지 확인 | T10~T12 live 검증 | 대기. 11/2 사용자가 API 키 발급을 신청했다(발급 전). 키 수령 후 환경변수 설정, 크레딧·결제 수단 적용, 초과 비용 한도, 전송/보관 동의 및 사용자 live 실행 승인이 필요하다. 키 조회·live 호출은 하지 않았다. |
| H3 | 테스트 Meta 앱·광고 계정·페이지·토큰 준비 | T13 live 검증, T15 | 대기. 실제 계정·권한·목적·CTA/destination·Graph 버전·KRW 예산·일정 및 사용자 실행 승인이 필요하다. 계정 연동은 하지 않았다. |
| H4 | 데모 영상 촬영·제출 (사람이 직접) | T16 | 대기. 공개 포털 경로는 확인했으나 양식은 로그인 뒤에 있다. 참가자가 제출 요구사항을 확인하고 직접 촬영·제출한다. |
