# AdLoom STATUS

한 줄 형식: `날짜 · 태스크 · 결과(DONE/BLOCKED, AC) · 남은 위험`

예: `2026-10-27 · T03 crop.py · DONE (AC-06,07,09) · 남은 위험: SAFE_TOP/BOTTOM 미확인`

---

2026-10-23 · 스펙 작성 · SPEC.md v0.1 초안, TASKS 전부 TODO · 남은 위험: SPEC.md §9 미확정 사항 14건, H1 Official Rules 미공개
2026-10-23 · BMAD 기획 구체화 · 검토 패키지 작성(8 capabilities, 기존 AC21개 연결, 추가 경계 시나리오18개), 공식 API·OSS 조사 및 문서 링크/지원 스크립트 smoke 확인 · 남은 위험: SC-001~010 미승인, H1~H4 대기; 제품 구현·AC 검증·live 호출 없음, 원본 SPEC/TASKS 유지
2026-10-24 · 제품 완성도 중심 기획 보완 · 고객 검증 gate 제외, 웹 전과정·원본 근거/제한 편집 CAP-9·PQ01~PQ10·개발/평가 12개 사례 계획, 초기 실연동/마지막 2일 검증 순서 반영; 문서 ID/AC 연결/로컬 링크·BMAD 설정 smoke 및 시간축 계산 통과 · 남은 위험: SC-001~013 원본 미반영, H1 사전개발 규정·H2/H3 실연동·H4 제출 조건 미확인; 제품/데이터/UI/live 검증은 미실행
2026-10-25 · 아키텍처·재사용 baseline · AD-1~14·모듈/API/저장/복구 계약 설계, Python3.12.15+직접9개 의존성 lock/sync, 공식 SAM parser source·Noto Sans KR/OFL·license/해시 확보, parser/font/ffmpeg/Range/SSE/OS lock 및 추가 경계 smoke 확인; 독립3관점 리뷰의 상태·mode·복구·업로드 경계 지적 반영 · 남은 위험: SC-001~014 원본 미반영, H1~H4와 실제 API/제품 UI/전체pipeline 미검증; T00~T16 미완료, push 없음
2026-10-25 · 스키마 구현 · 공유 Pydantic 모델44개·순수 근거/승인 검증, typed package·Makefile·회귀51개 구현; ruff/mypy strict/pytest 통과, 설치 패키지 JSON round-trip·44개 JSON Schema·FastAPI ASGI200/422 smoke 확인 · 남은 위험: config/LIVE gate·저장/worker/API·실제 권한/파일 hash 검증 미구현; T00/T01 부분 진행, 원본 SPEC 및 live gate 유지
