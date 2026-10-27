# third_party

외부 원본 자료를 수정 없이 보관한다. 출처·커밋·SHA-256·바이트 수·라이선스는 [`manifest.json`](manifest.json)에 있다. 선정 근거는 [`research/oss.md`](../research/oss.md), 런타임 의존성 핀은 `pyproject.toml`·`uv.lock`과 `docs/architecture/dependencies.md`에서 관리한다.

| 경로 | 내용 | 라이선스 |
| --- | --- | --- |
| `meta-sam-parser/meta_sam_parser-0.1.0.tar.gz` | 공식 SAM 3 Python 파서 0.1.0 source distribution 원본 | SAM License |
| `meta-sam-parser/LICENSE` | 위 archive 안의 LICENSE를 그대로 추출한 사본 | SAM License |
| `fonts/noto-sans-kr/NotoSansKR[wght].ttf` | Google Fonts 원본 가변 폰트 1개(wght 100~900) | SIL OFL 1.1 |
| `fonts/noto-sans-kr/OFL.txt` | 위 폰트의 저작권·라이선스 원문 | SIL OFL 1.1 |

## 지켜야 할 조건

- 파일 이름·내용을 바꾸지 않는다. 바꾸면 `manifest.json`의 해시와 "원본" 표기가 무효가 된다.
- 이 디렉터리 일부를 다른 사람에게 배포할 때는 해당 라이선스 파일을 함께 넣는다.
  - SAM License 1.b.i: SAM Materials 또는 파생물을 배포할 때 이 계약 조건으로만 배포하고 계약서 사본을 제공한다. MIT 같은 허용 라이선스가 아니며 사용 목적 제한(Trade Controls 등)과 역공학 조장 금지 조항이 있다.
  - OFL 1.1: 폰트 단독 판매 금지, 저작권·라이선스 고지 동봉, 수정본에 Reserved Font Name 'Source' 사용 금지.
- 확보는 사용 승인이 아니다. 해커톤 공식 규정(TASKS.md H1)이 외부 코드·폰트 사용을 허용하는지는 확인되지 않았다.
