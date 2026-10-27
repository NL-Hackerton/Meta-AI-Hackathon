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
| T04 | TODO | `policy.py` 규칙 기반 점검과 순화 (규칙 표는 `policy_rules.yaml`) | T01 | `policy.py`, `policy_rules.yaml` | AC-05 | 10/25 | |
| T05 | TODO | 어댑터 Protocol 5개 + Mock 5종 + 팩토리 | T01 | `adapters/base.py`, `adapters/mock_*.py` | AC-21 | 10/25 | |
| T06 | TODO | 스테이지: 입력·이해·추적·보강 | T02, T03, T04, T05 | `stages/` | AC-01, 02, 03, 04, 08, 10 | 10/25 | |
| T07 | TODO | `render.py` + 조립 스테이지: ffmpeg 렌더, 훅·자막·엔드카드 오버레이, 폰트 | T03 | `render.py`, `stages/assemble.py` | AC-11, 12, 13, 14 | 10/25 | |
| T08 | TODO | Marketing Mock과 게시 스테이지, 멱등성 | T02, T05 | `stages/publish.py` | AC-15, 16, 17 | 10/25 | |
| T09 | TODO | `cli.py`와 파이프라인 오케스트레이터, mock E2E | T06, T07, T08 | `cli.py`, `pipeline.py` | AC-20 | 10/25 | |
| T10 | TODO | Live Spark 어댑터 (**H2**) | T09 | `adapters/spark.py` | live 테스트, AC-03·04를 Live 응답 fixture로 재검증 | 10/27 | |
| T11 | TODO | Live SAM 어댑터, 마스크 → 박스 변환 (**H2**) | T09 | `adapters/sam.py` | live 테스트, AC-06 재검증 | 10/28 | |
| T12 | TODO | Live Image·Voice 어댑터 (**H2**) | T09 | `adapters/image.py`, `voice.py` | live 테스트, AC-10 | 10/29 | |
| T13 | TODO | Live Marketing 어댑터 (**H3**) | T09 | `adapters/marketing.py` | live 테스트, AC-16·17 재검증 | 11/2 | |
| T14 | TODO | 웹 승인 화면: 변형 6개 미리보기, `degraded`·정책 플래그 표시, 승인 버튼 → `approval.json` | T09 | `web/` | AC-15 (웹 경로) + 수동 확인 | 10/30 | |
| T15 | TODO | 실영상 LIVE 리허설: 실제 점포 영상 1~2건 전 과정, 실패 기록 | T10~T13, T14 | `docs/rehearsal.md` | 완료 정의(§1) | 11/3 | |
| T16 | BLOCKED | 제출물: README, 데모 대본·촬영 체크리스트 (**H1, H4**) | T15 | `README.md`, `docs/demo.md` | — | 11/4 | 10/27 Official Rules 원문을 확인했다. 원본 9절의 미공개 기록과 달라 원본 7절에 따라 SC-016을 제안했다. H1 참가자 수락·사전 자체 코드 조건, H4 로그인 뒤 제출 형식 확인 및 T15 완료를 기다린다. |

## 사람 게이트

| 게이트 | 내용 | 막히는 태스크 | 상태 |
| --- | --- | --- | --- |
| H1 | Official Rules 확인(10/26 전 공개): 허용 모델, 기존 코드 사용, 제출 형식 | T16 | 원문 확인(10/27, SC-016). 참가 승인·자격·약관 수락, 사전 자체 코드 조건, 로그인 뒤 제출 형식은 대기한다. |
| H2 | API 키 발급·환경변수 설정, 한국에서 호출 가능한지 확인 | T10~T12 live 검증 | 대기. Model API 접근·결제 수단·크레딧 적용·초과 비용 한도·전송/보관 동의 및 사용자 실행 승인이 필요하다. 키 조회·live 호출은 하지 않았다. |
| H3 | 테스트 Meta 앱·광고 계정·페이지·토큰 준비 | T13 live 검증, T15 | 대기. 실제 계정·권한·목적·CTA/destination·Graph 버전·KRW 예산·일정 및 사용자 실행 승인이 필요하다. 계정 연동은 하지 않았다. |
| H4 | 데모 영상 촬영·제출 (사람이 직접) | T16 | 대기. 공개 포털 경로는 확인했으나 양식은 로그인 뒤에 있다. 참가자가 제출 요구사항을 확인하고 직접 촬영·제출한다. |
