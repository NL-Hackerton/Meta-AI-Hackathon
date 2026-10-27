수정한 범위만 다시 봤고 판정은 **통과**입니다. critical·high는 없고, 남은 것은 차단 사유가 아닌 medium 1건입니다. 문서만 대조했고 검사나 테스트는 돌리지 않았습니다.

**해소 확인**
- **편집 전이:** codebase §4.1 표가 상태의 상한이 됐습니다. 실제 상태는 현재 완료 상태와 비교해 더 이른 쪽을 쓰고, failed_stage/error를 보존한 채 pending_stage부터 재개합니다. 그래서 assemble이 실패한 뒤 본문만 고쳐도 승인 대기로 올라가지 않습니다. AD-14와도 일치합니다.
- **PublishPlan 생성 시점:** create와 refresh에서만 만들고, approve와 publish는 현재 config와 비교만 합니다. fixture는 mock profile을 쓰고 live gate는 live에만 적용된다는 점이 §4.2와 AD-14에서 일관됩니다.
- **Model Files 재업로드:** resume_job의 `new_upload_attempt`로 명시한 경우에만 1회 다시 올립니다. 이전 시도 ID, UNKNOWN 상태 확인, 원격 잔존 동의, 실행자를 기록하고, 옵션 없는 resume은 재업로드하지 않습니다. §3.1과 AD-13이 일치합니다.
- **게시 후 변경:** codebase, product-flow, implementation-contracts 모두 "새 job"으로 통일됐고 같은 job에서 갈라지는 명령은 없습니다.
- **순환 참조:** PublishPlan에서 승인 digest를 빼서 승인 대상과의 순환 참조가 사라졌습니다.

**남은 문제 [medium, 직접 모순]**
- **위치:** implementation-contracts.md L34의 PublishPlan 행에 "9:16 A/B asset·thumbnail digests"가 아직 남아 있습니다.
- **충돌:** plan은 create/refresh에서만 만들어지므로, create 때는 렌더된 자산이 없습니다. 편집 후 다시 렌더해도 plan은 갱신되지 않아 이 값이 비어 있거나 낡게 됩니다.
- **결과:** publisher가 이 값을 읽으면 승인 대상의 자산 hash와 어긋납니다. 게시 직전 hash 검사가 있어 잘못된 게시보다는 게시 실패나 구현 차이로 나타납니다.
- **수정:** PublishPlan에서 asset·thumbnail digests를 빼고, 게시 자산은 승인 대상(ApprovalSubject)에 있는 9:16 A/B·thumbnail hash만 쓴다고 적으면 됩니다.

같은 내용을 `agent://Main`에도 보냈습니다.
