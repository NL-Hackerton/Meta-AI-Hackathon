# 리뷰 반영 기록

독립 reviewer 3개가 capability coverage, 공식 근거/라이선스, 상태·프로세스 seam을 검토했다. 초기 원문과 최종 집중 재검토 응답을 같은 디렉터리에 보존한다. 제품 구현 검증은 아니다.

- 초기 high: worker lease/handshake, edit rollback, UNKNOWN 해소, remote Files lifecycle, mode 결합, ApprovalSubject 기준값을 AD-2~5·11·13·14와 codebase에 반영했다.
- 공식 근거 검토는 수정 후 통과했다. SSE prebuffer·압축·예외 cause·upload spool·FFmpeg build·전이 라이선스를 정정했다.
- coverage/seam 재검토의 마지막 조건: 실패 후 본문 편집 상태 상승, fixture gate, upload UNKNOWN 경로를 수정했다. 실패 기록/pending_stage 보존, 명시 fixture profile, 명시 new_upload_attempt1회를 규정했다.
- 최종 응답에 남은 medium인 PublishPlan의 렌더 자산/생성 시점 모순은 자산을 ApprovalSubject로 옮기고 create/refresh/게시설정edit에서만 plan을 snapshot하도록 반영했다. env profile 교체는 명시 refresh만 허용한다. low인 fixture 버튼 조건도 live 조건과 분리했다.
- core source의 PublishPlan 내부 승인 digest도 제거해 순환 참조를 막았다. 게시 후 변경은 새 job으로 통일했다.
- 최종 mechanical lint: findings0, AD14개, CAP9개 연결. 계약은 설계 기준선으로 마감하되 SC-001~014 원본 반영·H1~H4는 미해제다.

실제 실행한 외부 baseline 범위는 docs/architecture/baseline-verification.md에 있다. 제품 서버·CLI·provider live 호출은 아직 없다.
