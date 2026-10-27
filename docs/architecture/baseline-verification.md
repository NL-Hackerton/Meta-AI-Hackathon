# 재사용 baseline 실행 확인

현재 ffmpeg/ffprobe binary·configuration 원본 기록은 [media-baseline.json](media-baseline.json)에 있다.

검토 후 추가한 경계 실험: HTTPX public byte-stream cap이 newline 없는 SSE를 event 생성 전에 중단함을 확인했고, 공식 parser가 timeout·quota 예외를 ResponsesStreamSourceError.cause로 보존함을 확인했다. 30000/1001fps의 프레임 시작/끝 경계 3,000개와 NFC codepoint3/UTF-16 code unit4 사례도 계산으로 확인했다. 이는 제안된 wrapper·변환 규칙의 독립 실험이며 제품 adapter 구현 검증이 아니다. 결과는 같은 진단 폴더의 review-boundaries.json에 있다.

실행일: 2026-10-25. **외부 라이브러리·폰트·시스템 기능만 확인했다. AdLoom 제품 서버·CLI·영상 파이프라인·실제 Meta API를 구현하거나 검증한 결과가 아니다.** 유료 API·광고 생성·고객 데이터는 사용하지 않았다.

## 실제 실행 결과

| 대상 | 실행한 경로 | 관측 결과 |
| --- | --- | --- |
| 설치 핀 | `.venv/bin/python`에서 distribution metadata를 pyproject의9개 직접 의존성과 대조 | 9개 모두 정확한 version 일치 |
| 출처 무결성 | third_party manifest의 크기/SHA256 검사, sdist 내 소스와 설치된 parser 비교 | 외부4개 파일 일치, parser의9개 source/typing 파일이 설치본과 byte 단위 일치 |
| SAM 정상 파싱 | upstream README의 실제 예제 text를17byte chunk로 분할하여 공식 parser 실행 | box2/mask2, object IDs0/1, frame0. 첫 box `(211,228,271,255)`로 half-open 변환 확인 |
| SAM 경계 | zero-match 완료, EOF 미완료, box만 있고 mask 없는 malformed line | completed empty / incomplete eof / malformed_record 진단을 구분. malformed여도 outcome이 completed일 수 있어 diagnostics 검사 필요 |
| 한글 폰트 | 원본 NotoSansKR variable TTF를 Pillow에서 weight600으로 렌더 | 720×200 PNG 생성. 한글4글자의 mask 구별 확인 및 PNG 직접 열람에서 두 줄 글자·중간점·숫자 정상 표시 |
| 미디어 인코딩 | 위 PNG+무음으로 ffmpeg H.264/yuv420p + AAC44.1kHz stereo 영상 생성 | 1초·30frame, ffprobe codec/size/audio 확인 |
| 결정론 범위 | 같은 입력·폰트·현재 ffmpeg build로 두 번 렌더하여 decoded frame MD5 목록의 SHA256 비교 | 두 결과 동일. 다른 OS/build·실제 모델 출력의 결정론은 입증하지 않음 |
| 미디어 HTTP | 실제 FastAPI/Starlette FileResponse를 HTTPX ASGITransport로 호출 | bytes0-31은206·정확32bytes, 범위 밖은416 |
| SSE | 실제 StreamingResponse→httpx-sse로 comment/event/multiline data 처리 | sample event1개, JSON value7. 외부 provider 호출 없음 |
| process lock | 부모 flock fd를 자식에 상속한 뒤 부모 fd를 닫고 별도 fd로 lock 시도 | 자식 생존 동안 두 번째 소유자 거부, 자식 종료 뒤 획득 성공 |

실행 환경은 CPython3.12.15·macOS arm64, ffmpeg/ffprobe9.0.2다. ffmpeg의 Homebrew build는 GPL·libx264·version3 옵션을 포함한다. 바이너리 재배포 라이선스 의무를 LGPL-only로 축약하지 않는다.

decoded frame 목록 digest: `b15e38f11fc783c177b3985b6b4c317d60a9fa4dd4bd0712220ba6d61fb26f76`.

## 로컬 진단 산출물

Git 제외 `data/baseline-smoke-kv0471he/`에 `results.json`, `hangul.png`, `render-1.mp4`, `render-2.mp4`와 lock 진단 파일을 보관했다. 이 파일은 제품 평가12개 세트가 아니며 고객용 광고나 최종 demo 소재도 아니다. 실행 코드는 임시 interpreter 입력으로 사용해 repository에 앱 scaffold·테스트 골격을 남기지 않았다.

## 확인하지 않은 것

- SAM 실제 네트워크 stream, 모델 품질·지연·한국 접근성, H2 비용/권한.
- 전체 AdLoom renderer의6개 비율/훅 출력과 실제 영상의 crop·자막 품질.
- 실제 제품 웹 UI·브라우저 재생·접근성·보안. HTTP baseline은 in-process ASGI로 실행했다.
- approval·revision·job 저장 구현, crash recovery, Marketing API·PAUSED 객체 생성.
- 다른 장비·운영체제에서의 설치와 같은 frame hash.
- H1 대회 규정·외부 코드/사전 개발 허용, H4 제출 요구.

## 재현 입력의 출처

- [공식 SAM Python0.1.0](https://pypi.org/project/meta-sam-parser/0.1.0/) 및 보관한 sdist의 README Direct parser API 예제.
- [FileResponse 계약](https://starlette.dev/responses/), [httpx-sse](https://github.com/florimondmanca/httpx-sse), [fcntl](https://docs.python.org/3.12/library/fcntl.html).
- 설치·버전은 [dependencies.md](dependencies.md), 원본 파일 hash·license는 [third_party manifest](../../third_party/manifest.json).
