---
name: agent-friendly-check
description: 본 프로젝트는 사람이 아닌 다른 AI agent가 호출하는 도구다. 코드·설정·워크플로우·출력 포맷·CLI 플래그 변경 후 invoke해서 agent 인터페이스 계약(discoverability, parseability, side-effect 선언, 결정성)이 깨지지 않았는지 검사하고 회귀를 신고한다.
---

# Agent-Friendly Check

본 프로젝트의 1차 사용자는 **사람이 아니라 다른 AI agent**다. agent는 다음을 전제로 도구를 다룬다:

- `--help`만 보고 능력을 파악
- 인터랙티브 입력은 절대 불가, exit code와 stdout 파싱으로 결과 판단
- 부작용(파일 쓰기·이메일·과금 API 호출)은 호출 전에 선언되어 있어야 한다
- 같은 입력은 가능한 한 같은 출력을 낸다

이 스킬은 변경이 위 전제를 깨지 않았는지 검사한다.

## 언제 호출하나

다음 중 하나라도 변경된 직후, 또는 사용자가 "agent-friendly 검사" 류로 명시적으로 요청할 때:

- `weekly_monitor.py` / `monitor.py`의 CLI 플래그·argparse 시그니처
- `discovery.py` / `notifier.py`의 public 함수 시그니처 또는 반환 형태
- 표준 출력·에러로 나가는 메시지 포맷, 리포트 파일명/스키마
- `channels.yaml` / 도입 예정인 `config.yaml`의 키 추가·삭제·이름 변경
- `.github/workflows/*.yml`의 invocation 명령
- 새 외부 의존성 추가, 새 부작용(쓰기·네트워크·과금) 추가

UI/렌더링만 바꾼 변경(예: 리포트 본문 문구)에는 호출하지 않아도 된다.

## 검사 절차

1. `git diff origin/main...HEAD` 또는 직전 커밋 대비 변경 파일 목록 확보
2. 변경 파일이 아래 카테고리 A~G 중 어디에 해당하는지 매핑 (해당 없는 카테고리는 skip)
3. 각 항목을 **PASS / WARN / FAIL**로 판정
   - PASS: 기준 충족
   - WARN: 합리적 사유가 있거나 향후 작업으로 정리 가능
   - FAIL: agent 호출 시 즉시 깨짐 — 수정 권장
4. 마지막에 "보고 형식"대로 요약 + FAIL별 구체적 수정 제안

## 검사 항목

### A. 인터페이스 계약 (CLI·진입점 변경 시)
- `python <entry> --help`가 비대화식으로 떨어지고 모든 플래그에 설명이 있는가
- 모든 플래그에 long form이 있는가 (`-x` 단독 금지 — agent가 추측 못 함)
- `input()`, `getpass()`, `click.prompt()` 등 인터랙티브 호출 없음
- 미실행 모드 존재 (`--dry-run` 또는 동급의 `--no-process` + `--no-email`)
- 새 부작용을 추가했다면 미실행 모드에서도 그 동작이 시뮬레이션·로그됨
- 파괴적 동작은 명시적 플래그(`--yes`, `--force`)를 요구하거나 default가 안전

### B. 출력·exit code (출력 포맷 변경 시)
- 에러는 stderr, 결과·로그는 stdout (혹은 명확히 구분)
- 성공 0, 실패 비0 — 부분 실패도 0이 아닌 코드로 구별
- 마지막에 파싱 가능한 요약 한 줄 (예: `RESULT processed=10 failed=2 report=reports/2026-W17.md`)
- 또는 `--output json` 플래그로 구조화 출력 지원
- 에러 메시지는 "무엇이 실패했고, 다음에 무엇을 할지" 둘 다 포함
- 영상별·채널별 부분 실패가 stdout/리포트에 노출되며 silent하게 묻히지 않음

### C. 부작용·안전성 (새 동작 추가 시)
- README/CLAUDE.md에 부작용 목록 명시: 어떤 파일을 쓰고, 어떤 외부 호출을 하고, 어떤 비용이 드는지
- 모든 외부 네트워크 호출에 timeout
- 새 부작용은 미실행 모드로 차단 가능
- 비용 상한이 설정 가능하거나 최소한 호출 전 추정치를 노출

### D. 설정 가능성 (config·상수 변경 시)
- 모든 동작 상수(top_n, lookback_days, Whisper 파라미터 등)가 config 또는 CLI로 노출, 코드에 매직 넘버 신규 추가 금지
- config 스키마 추가 시 `config.example.yaml`(도입 후) 동기화
- 필요한 env var는 시작 시점에 일괄 검증, 처리 도중에 발견되어 한참 뒤에 죽지 않음
- 같은 input + config + 같은 영상 → 결정적 결과 (Whisper 등 본질적 비결정성은 명시)

### E. 관측성
- 로그 한 줄에 stage·channel·video_id 같은 grep 가능한 토큰 포함
- 장시간 동작에 진행 표시 (몇 / N 처리 중)
- 비용·실행시간 메트릭이 결과나 리포트에 포함

### F. agent용 문서
- README 또는 별도 파일에 "For AI Agents" 섹션 존재
- 호출 예시: 한 명령으로 dry-run, 한 명령으로 full
- 출력 스키마(파일 경로, JSON 구조, 마지막 RESULT 라인) 명시
- 환경 의존성(`ffmpeg`, env vars, Python 버전)이 한 곳에 모임
- 새 플래그 추가 시 위 섹션도 같이 업데이트

### G. 안정성
- 기존 CLI 플래그 제거/이름 변경은 deprecation warning을 1릴리스 이상 둠
- config key 변경 시 마이그레이션 경로 또는 명시적 에러 메시지

## 보고 형식

```
[Agent-Friendly Check]
변경 파일: <list>
적용 카테고리: <A,B,...>

A. 인터페이스 계약
  PASS  --help 정상 동작
  FAIL  새 플래그 --foo가 dry-run 시 시뮬레이션되지 않음
        수정 제안: --no-process 분기에 plan-only 출력 추가

D. 설정 가능성
  WARN  env var 검증이 process_video 진입 시점에 발생 — 시작 직후로 옮기는 게 안전

종합: FAIL <n> / WARN <n> / PASS <n>
다음 단계: <FAIL이 있으면 그 수정부터, 없으면 commit 진행 가능>
```

## 현재 알려진 미충족 (참고)

원래의 baseline FAIL 5건 + WARN 2건은 Step 1~4 + Action 1~3 작업으로 모두 해소됨. 새 FAIL/WARN이 발견되면 회귀로 간주.

다음 라운드 후보 (계약 자체 FAIL은 아님):
- 채널 health 모니터 (RSS 빈 채널 N주 연속 알림) — F-카테고리 운영 가시성
- machine-readable manifest (`agent.json` 등) — F-카테고리, MCP server wrapping 결정 시

## 자동화: pytest contract 검사

`tests/test_cli_contract.py`가 본 스킬의 핵심 항목(A: --help / no interactive, B: RESULT 라인 / exit code, D: env 검증)을 자동 검증한다. 변경 후 `pytest tests/test_cli_contract.py -v`만 돌려도 큰 회귀는 잡힌다. 이 스킬은 그 위에 사람·문서 영역(F: README, C: 부작용 목록)을 추가로 점검하는 layer.
