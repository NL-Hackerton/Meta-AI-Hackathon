# AdLoom STATUS

한 줄 형식: `날짜 · 태스크 · 결과(DONE/BLOCKED, AC) · 남은 위험`

예: `2026-10-27 · T03 crop.py · DONE (AC-06,07,09) · 남은 위험: SAFE_TOP/BOTTOM 미확인`

---

2026-10-23 · 스펙 작성 · SPEC.md v0.1 초안, TASKS 전부 TODO · 남은 위험: SPEC.md §9 미확정 사항 14건, H1 Official Rules 미공개
2026-10-23 · BMAD 기획 구체화 · 검토 패키지 작성(8 capabilities, 기존 AC21개 연결, 추가 경계 시나리오18개), 공식 API·OSS 조사 및 문서 링크/지원 스크립트 smoke 확인 · 남은 위험: SC-001~010 미승인, H1~H4 대기; 제품 구현·AC 검증·live 호출 없음, 원본 SPEC/TASKS 유지
2026-10-24 · 제품 완성도 중심 기획 보완 · 고객 검증 gate 제외, 웹 전과정·원본 근거/제한 편집 CAP-9·PQ01~PQ10·개발/평가 12개 사례 계획, 초기 실연동/마지막 2일 검증 순서 반영; 문서 ID/AC 연결/로컬 링크·BMAD 설정 smoke 및 시간축 계산 통과 · 남은 위험: SC-001~013 원본 미반영, H1 사전개발 규정·H2/H3 실연동·H4 제출 조건 미확인; 제품/데이터/UI/live 검증은 미실행
2026-10-25 · 아키텍처·재사용 baseline · AD-1~14·모듈/API/저장/복구 계약 설계, Python3.12.15+직접9개 의존성 lock/sync, 공식 SAM parser source·Noto Sans KR/OFL·license/해시 확보, parser/font/ffmpeg/Range/SSE/OS lock 및 추가 경계 smoke 확인; 독립3관점 리뷰의 상태·mode·복구·업로드 경계 지적 반영 · 남은 위험: SC-001~014 원본 미반영, H1~H4와 실제 API/제품 UI/전체pipeline 미검증; T00~T16 미완료, push 없음
2026-10-25 · 스키마 구현 · 공유 Pydantic 모델44개·순수 근거/승인 검증, typed package·Makefile·회귀51개 구현; ruff/mypy strict/pytest 통과, 설치 패키지 JSON round-trip·44개 JSON Schema·FastAPI ASGI200/422 smoke 확인 · 남은 위험: config/LIVE gate·저장/worker/API·실제 권한/파일 hash 검증 미구현; T00/T01 부분 진행, 원본 SPEC 및 live gate 유지
2026-10-27 · 재개 점검 · BLOCKED(신규 완료 AC 없음) · T00·T01은 IN_PROGRESS이고 선행이 모두 DONE인 TODO는 계산 결과 0개다. 원본 7절의 선택 규칙에 따라 구현 루프를 시작하지 않았으며, 부분 진행 태스크 재개와 기존 스키마 계약의 후속 적용을 SC-017로 제안했다. T00~T09 완료를 주장하지 않는다.
2026-10-27 · H1·T16 · BLOCKED（Official Rules 원문 확인, 참가자 확인 대기） · Meta 행사 페이지는 공개 예정 문구를 유지하지만 연결된 https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver 에서 규정 전문을 브라우저로 확인했다. Impact 30%·Meta AI Tooling 25%·Technical Depth & Execution 20%·Demo 25%, 라이선스 준수 및 확장 조건의 OSS 사용 허용을 SC-016에 기록했다. 사전 자체 코드 조건·참가 승인/자격·약관 수락은 미확인이다.
2026-10-27 · H2·H3 · BLOCKED（사용자 실행 승인 대기） · Credit Terms에서 Model API 결제 수단 요구·$150 소진 후 과금·크레딧 신청 선택 사항을 확인했다. 한국 계정의 모델 접근, Muse Voice 사용 범위, 비용 한도·데이터 전송/보관 동의와 실제 광고 계정·권한·목적·CTA/destination·Graph 버전·KRW 예산·일정은 확인이 필요하다. 키 조회·live 호출·광고 계정 연동은 하지 않았다.
2026-10-27 · H4 · BLOCKED（로그인 뒤 제출 형식·직접 촬영/제출 대기） · 공식 제출 경로 https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit 은 비로그인 브라우저에서 로그인 화면으로 이동했다. 영상 길이·언어·파일 형식·저장소 공개 여부는 미확인이다. 공식 11월 4일 21:00 ET를 시간대 데이터로 변환한 11월 5일 11:00 KST는 원본 마감과 일치한다.
2026-10-27 · 진행 요약 · 규정 대조와 재개 차단 원인 기록 완료 · SPEC·제품 코드·테스트는 변경하지 않았다. make check·INV·mock E2E는 이번에 실행하지 않았고 신규 완료 AC는 없다. 원본 9절의 영상/문구 한도·CTA·안전 영역·광고 규격·API 설정은 잠정값이며, 기존 API 확인 장부의 문서 확인과 실제 호출 검증을 구분한다. 무거운 계산은 수행하지 않았고 향후 해당 계산은 5080 서버를 사용한다. 다음 조치는 SC-016·017 및 관련 계약 제안 검토 후 T00부터 재개하는 것이다.
2026-10-27 · T00 · DONE(AC-19) · 사용자 기획 반영·코드 수정 지시로 부분 진행 태스크를 재개했다. 합성 생성기 실패 테스트→구현→make check 53개 통과 및 data/sample.mp4의 H.264·1920×1080·300프레임·10초를 확인했다. 기존 스키마를 재사용하고 원본 SPEC는 보존한다. 사람 게이트·live 실행 제한은 유지한다.
2026-10-27 · T01 · DONE(AC-01 스키마·18·21 설정 경계) · 실패 테스트 후 config·Standard 모델 제한·live 차단을 구현했다. make check 55개와 설정 로드 smoke 통과. 실제 어댑터 팩토리 경계는 T05에서 검증하며 H2/H3는 유지한다.
