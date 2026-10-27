# AdLoom 반영 범위 최종 판정

이번에 고친 범위만 다시 읽었습니다. 대상은 `codebase.md` §3.1·§4·§4.1·§4.2·§5, spine AD-13·14, implementation-contracts L34·L94·L96, product-flow L166·L185입니다. 실행이나 검사는 하지 않았습니다.

## 이전 지적 3건은 해소되었습니다
| 항목 | 상태 | 확인 근거 |
|---|---|---|
| 편집 후 상태가 렌더를 건너뛰어 올라가는 문제 | 해소 | §4.1 L94·L105: 표는 상한이고 현재 완료 상태와의 최솟값을 씁니다. failed_stage/error를 보존하고 pending_stage에서 재개합니다. "current6개가 없는 편집은 승인 대기로 바로 전이하지 않는다"도 명시되어 있습니다. |
| fixture 승인과 AC-20 | 해소 | §4.2 L113·L117, AD-14: mock profile을 쓰고 live gate는 live job에만 적용합니다. |
| Model Files 업로드 UNKNOWN 해소 | 해소 | §3.1 L84, AD-13: `new_upload_attempt`로 1회만, 잔존 동의와 actor를 기록하고 이전 UNKNOWN 정리 경고를 보존합니다. |
| 게시 후 변경 | 해소 | codebase L73·L90, impl-contracts L96, product-flow L166·L185가 모두 "새 job"으로 같습니다. |
| ApprovalSubject 순환 참조 | 해소 | impl-contracts L34에서 PublishPlan 안의 승인 digest를 뺐습니다. |

## 이번 수정으로 생긴 직접 모순 1건 [medium]
**PublishPlan을 만드는 시점과 PublishPlan에 들어가는 내용이 맞지 않습니다.**

- **위치:**
  - codebase L113: "PublishPlan은 create 또는 refresh_publish_plan에서만 snapshot."
  - implementation-contracts L34: PublishPlan에 "9:16 A/B asset·thumbnail digests"가 들어갑니다.
  - §4.1 표의 한 행: "본문·제목·예산·destination·게시 profile 갱신 → 게시 계획 재검사."
- **충돌 1:** create 시점에는 렌더 결과가 아직 없습니다. 그래서 create에서 만든 plan에는 자산 digest가 없거나, 재렌더 뒤 낡은 값으로 남습니다. 게시 구현자가 L34대로 plan에서 업로드할 자산을 찾으면 자산이 없거나 이전 렌더 결과를 가리킵니다.
- **충돌 2:** `edit_job`으로 예산이나 destination을 바꿔도 plan을 다시 만들 수 없습니다. "create/refresh에서만"이라는 규칙 때문입니다. 그 결과 편집 경로와 refresh 경로가 서로 엇갈립니다.
- **최소 수정:** 두 군데 문구를 고칩니다.
  - impl-contracts L34: "PublishPlan은 계정, Page, Graph, profile, 예산, 통화, objective, 일정, CTA, destination 같은 설정값만 담는다. 게시할 9:16 A/B와 thumbnail의 digest는 ApprovalSubject 안의 현재 manifest RenderedVariant에서 가져온다."
  - codebase L113: "plan snapshot은 create, refresh, 그리고 게시 설정을 바꾸는 edit_job commit에서만 만든다."

## 참고 [low]
product-flow L158의 게시 버튼 "활성화 조건: live 모드, Marketing 자격, H3"를 글자 그대로 읽으면, fixture job에서는 mock 게시 버튼이 꺼집니다. 이는 L159와 §4.2의 "fixture는 mock publish로 완결"과 맞지 않습니다. 해당 조건 앞에 "live job의"를 붙이면 됩니다.

## 판정
- **판정:** 조건부 통과. critical과 high는 없습니다.
- **통과 조건:** 위 PublishPlan 문구 2곳(medium)을 반영하면 이번 수정 범위는 architecture gate 통과입니다. low 1건은 선택 사항입니다.
- **확신도:** 0.85. 문서 내용만 근거로 판단했으며, 제품 구현과 실행 검증은 없습니다.
