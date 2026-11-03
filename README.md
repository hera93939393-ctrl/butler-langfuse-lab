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
| `mock_2025_results.txt` | 가상 기관의 2025 실적 | 정답 |
| `mock_2024_results.txt` | 같은 항목의 2024 값 | 연도 헷갈림 |
| `mock_delegation_rules.txt` | 성과와 상관없는 규정 | 엉뚱한 자료 끌어오기 |

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

## 평가 (데이터셋과 채점)
오류 분석(`docs/error-analysis.md`)에서 찾은 실패를 같은 입력으로 다시 세려고 만든 데이터셋입니다.

| 파일 → Langfuse 데이터셋 | 무엇을 보나 | 채점 |
|---|---|---|
| `data/eval/find_sources.jsonl` → `butler-find` (9개) | 요청 읽기·자료 찾기: 연도, 모드, 골라야 할 줄 | 코드, 모델 호출 없음 |
| `data/eval/write.jsonl` → `butler-write-reply` (쓰기 6) · `butler-answer-reply` (물음 8) | 자료를 고정하고 글쓰기만: 숫자, 숨은 지시, 기준 적용 | 코드 9 + LLM 심사 5 |

- 프롬프트: 서비스 지시문을 Langfuse 프롬프트 `butler-write`, `butler-answer` 로 올림(`scripts/push_prompts.py`). 화면 실험은 프롬프트 하나에 데이터셋 하나라 모드별로 데이터셋을 나눴습니다.
- LLM 심사: `butler-reply-judge`(gpt-4o, Boolean). 지시문은 `docs/judge-prompt.md`, 규칙 `butler-reply-experiments` 가 두 데이터셋의 화면 실험에만 붙습니다.
- 코드 채점 점수 `code-check`: 화면 실험 뒤 `scripts/score_run.py <실험 이름>` 으로 붙입니다.
- `scripts/experiment.py` 는 같은 실험을 SDK 로 돌립니다. Langfuse 규칙이 SDK 실험에는 붙지 않아, 같은 심사 지시문·모델로 점수 `judge-sdk` 를 직접 붙입니다.

### 프롬프트 관리
서비스는 쓰기 지시문을 Langfuse 에서 라벨로 가져옵니다(`app/prompts.py`). `ENV=production` 이면 `production`, 그 밖(lab, local)은 `staging`. 키가 없거나 Langfuse 에 닿지 못하면 코드의 문장(`app/pipeline.py`)으로 답하고, 트레이스의 `write` 단계에 쓴 프롬프트 이름과 버전이 남습니다.

| 버전 | 내용 | 라벨 |
|---|---|---|
| 1 | 코드의 문장 그대로 | production |
| 2 | 1과 같은 내용(실수로 만든 사본) | — |
| 3 | `data/prompts/*.v2.txt`: 숨은 지시 무시, 합계 금지, 기준 적용, 요청 항목만, 오늘 기준 작년·올해 | staging |

배포·롤백은 코드 배포 없이 라벨을 옮깁니다. 새 버전은 `scripts/push_prompts.py --file <파일> "<메모>"`(라벨 없이 올라감) → 실험으로 비교 → 라벨 이동.

"작년·올해"는 오늘 날짜 기준으로 봅니다(2026-11-03 기준 올해=2026).

```
.venv\Scripts\python scripts/eval_find.py        (무료)
.venv\Scripts\python scripts/eval_write.py       (실제 LLM 14번)
.venv\Scripts\python scripts/upload_datasets.py  (다시 실행해도 항목이 늘지 않음)
```

## 배포 (Cloud Run)
비밀값(LLM 키, Langfuse 비밀키, 팀 비밀번호)은 Secret Manager에 두고 이름으로만 연결합니다. 최대 인스턴스 1개, 하루 요청 수 `DAILY_LIMIT`.
