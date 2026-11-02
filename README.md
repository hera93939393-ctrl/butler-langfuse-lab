# AI 한글집사 실습 (Langfuse 관측)

> **AI 한글집사 본 코드와 별개인 실습용 저장소입니다.** 실제 업무 자료는 넣지 않습니다. 자료는 모두 `mock_data/` 의 가상 자료이고, 서비스도 이 폴더 밖의 파일은 읽지 않습니다.

한글집사의 "자료 보고 쓰기(참고 작성)" 흐름만 떼어 와, 팀원이 배포된 주소에서 써 보고 그 기록을 Langfuse로 같이 분석하려고 만들었습니다.

## 무엇을 하나
1. 팀 비밀번호와 별명으로 입장
2. 참고할 가상 자료를 고르고 요청("2025년 점검 실적 찾아서 넣어줘")
3. 집사가 개조식으로 답하고, 답의 숫자가 자료에 있는지 **수치 확인**을 붙임
4. 답에 **좋아요 · 별로예요 · 신고** → Langfuse 점수

## 목업 자료와 일부러 넣은 함정
| 파일 | 내용 | 노리는 실수 |
|---|---|---|
| `가상_2025_사업성과.txt` | 가상 기관의 2025 실적 | 정답 |
| `가상_2024_사업성과.txt` | 같은 항목의 2024 값 | 연도 헷갈림 |
| `가상_전결규정.txt` | 성과와 상관없는 규정 | 엉뚱한 자료 끌어오기 |

## Langfuse 계측 구조
| 이름 | 종류 | 남기는 것 |
|---|---|---|
| `write-turn` | 트레이스 | 요청, 고른 자료, 최종 글, 모드, 수치 확인 결과 |
| `read-request` | span | 모드(쓰기/물음), 연도, 낱말 — 코드 규칙 |
| `find-sources` | span | 고른 줄, 점수, 자료 연도 |
| `write` | generation | 모델 이름, 입력·출력, 토큰 |
| `number-guard` | span | 자료에 있는/없는 숫자 (없으면 WARNING) |
| `user-feedback`, `report` | 점수(BOOLEAN) | 좋아요 1·별로예요 0, 신고 1 + 사유 |

속성: user = 별명, session = 별명 + 한국 날짜, environment = `ENV`, version = Cloud Run 리비전.
목업 자료만 쓰므로 원문을 남기되, 전화번호·이메일·카드 번호 모양은 보내기 전에 가립니다.
본체 한글집사는 실제 자료라 정반대로, 기록을 밖으로 보내지 않고 SQLite에 남기기로 했습니다.

## 분석할 질문
- 가장 오래 걸린 트레이스는? 어느 단계가 길었나?
- 가장 요금이 많이 나온 트레이스는? `write` 입력 토큰이 왜 컸나?
- 제대로 답하지 못한 트레이스는? (`별로예요`, `report`, `number-guard` WARNING 부터) 처음 어긋난 단계는 `find-sources` 인가 `write` 인가?

## 로컬 실행
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env   (값 채우기)
.venv\Scripts\pytest -q
.venv\Scripts\uvicorn app.main:app --port 8090
```

## 배포 (Cloud Run)
비밀값(LLM 키, Langfuse 비밀키, 팀 비밀번호)은 Secret Manager에 두고 이름으로만 연결합니다. 최대 인스턴스 1개, 하루 요청 수 `DAILY_LIMIT`.
