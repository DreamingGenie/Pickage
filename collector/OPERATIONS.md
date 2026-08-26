# 실시간 수집 운영 가이드

> 대상: 개인 노트북 또는 홈 서버에서 실시간 수집기를 상시 구동하는 경우
> 선행: [BRONZE_CONTRACT.md](BRONZE_CONTRACT.md) · [DATA_PLATFORM_PLAN](../docs/DATA_PLATFORM_PLAN_260826.md) 5-3절

## 왜 상시 구동이 필요한가

실시간 API는 공식 과거 조회 기능이 없다. 오늘 받지 못한 오늘치는 내일 quota를
남겨도 받을 수 없다. **수집기가 멈춘 시간만큼이 영구 손실**이다. 그래서 이
가이드의 목표는 "정확한 24시간 가동"이 아니라 **"멈추면 알아서 다시 뜨는 것"** 이다.

## 파이썬 경로 확인

자동 재시작 설정에는 **`python` 명령이 아니라 실행 파일의 절대 경로**가 필요하다.
systemd와 작업 스케줄러는 로그인 셸의 `PATH`를 물려받지 않으므로, `python`이라고만
적으면 "파일을 찾을 수 없음"으로 조용히 실패한다.

```bash
python -c "import sys; print(sys.executable)"
```

아래 예시는 2026-08-26 기준 이 저장소 개발 환경의 실측값이다. 가상환경을 쓰면
`<repo>/.venv/Scripts/python.exe`(Windows) 또는 `<repo>/.venv/bin/python`(Linux)로
바꾼다.

| 환경 | 경로 |
|---|---|
| Windows (전역 설치) | `C:\Users\<사용자>\AppData\Local\Programs\Python\Python312\python.exe` |
| Windows (콘솔 창 없이) | 같은 폴더의 `pythonw.exe` |

의존성은 `requests`와 `python-dotenv` 두 개뿐이다. 전역에 이미 있으면 가상환경은
필요 없다.

```bash
python -c "import requests, dotenv; print('OK')"
```

## 실행 전 확인

```bash
# 1. 설정 검증 — 활성 대상을 1회씩만 호출하고 끝난다
python -m collector.run_scheduler --once

# 2. 호출 없이 계획만 보고 싶으면 존재하지 않는 대상으로 필터
python -m collector.run_scheduler --once --only nonexistent   # 설정 오류 목록만 확인
```

`--once`가 통과하면 대상·키·파라미터·예산이 모두 유효하다. 실패한 대상이 있으면
종료 코드 1, 설정 오류면 2가 반환된다.

## 상시 실행

```bash
python -m collector.run_scheduler
```

- 로그: stderr + `data/logs/collector.log` (5MB × 5개 회전)
- 정지: `Ctrl+C` 또는 `SIGTERM` — 진행 중인 호출을 마치고 당일 요약을 남기고 종료한다
- quota 원장: `data/quota_ledger.json` — 재시작해도 당일 카운트가 이어진다

### 프로세스를 하나만 띄운다

**같은 원장을 쓰는 수집기 프로세스를 두 개 이상 띄우면 안 된다.**
`data/quota_ledger.json`에 파일 락이 없어서 `consume()`이 서로를 덮어쓴다.
당일 카운터가 실제보다 작게 집계되고, 상한 950을 넘겨 호출해 provider가 그날
수집을 차단한다. 대상을 나누고 싶으면 프로세스를 나누는 대신 `targets.toml`에
항목을 추가한다.

`--once`를 상시 프로세스와 동시에 돌리는 것도 같은 이유로 피한다. 수동 검증은
프로세스를 멈춘 뒤에 하거나, `retry_reserve`로 남겨둔 예비분 범위에서만 한다.

## 자동 재시작

### Linux 홈 서버 — systemd

`~/.config/systemd/user/jr-collector.service`

```ini
[Unit]
Description=Journey Reliability realtime collector
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/git/S15P21A506
ExecStart=%h/git/S15P21A506/.venv/bin/python -m collector.run_scheduler
Restart=always
RestartSec=30
# 로그는 수집기가 직접 파일에 쓰므로 journal에는 중복 저장하지 않는다.
StandardOutput=null
StandardError=null

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now jr-collector
systemctl --user status jr-collector

# 재부팅 후에도 뜨게 한다 (로그인 없이 user 서비스 유지)
sudo loginctl enable-linger "$USER"
```

`enable-linger`가 없으면 로그아웃 시 서비스가 함께 죽는다. 홈 서버에서 가장
흔한 누락 지점이다.

### Windows 노트북 — 작업 스케줄러

`pythonw.exe`로 띄워 콘솔 창이 뜨지 않게 한다.

```powershell
$py   = "C:\git\S15P21A506\.venv\Scripts\pythonw.exe"
$act  = New-ScheduledTaskAction -Execute $py -Argument "-m collector.run_scheduler" `
          -WorkingDirectory "C:\git\S15P21A506"
$trg  = New-ScheduledTaskTrigger -AtLogOn
# 비정상 종료 시 1분 뒤 재시도를 무제한 반복하고, 실행 시간 제한을 없앤다.
$set  = New-ScheduledTaskSettingsSet -RestartInterval (New-TimeSpan -Minutes 1) `
          -RestartCount 9999 -ExecutionTimeLimit ([TimeSpan]::Zero) `
          -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
          -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "JR-Collector" -Action $act -Trigger $trg -Settings $set
```

`-MultipleInstances IgnoreNew`가 중요하다. 이게 없으면 로그인할 때마다 프로세스가
추가로 떠서 위에서 말한 원장 경쟁이 발생한다.

절전·최대절전에서 복귀하면 수집기가 스스로 다음 슬롯부터 이어간다. 놓친 슬롯을
몰아서 호출하지는 않는다(실시간은 따라잡기가 불가능하고 quota만 태운다).
노트북 절전은 그만큼 데이터 공백으로 남으므로, 상시 가동이 목적이면 절전을 끄거나
홈 서버 쪽을 쓴다.

## 정상 동작 확인

### 로그에서 볼 것

| 로그 | 의미 |
|---|---|
| `예산 <풀> N회/일 / 상한 950` | 기동 시 계획 검증. `** 초과 **`가 붙으면 `targets.toml`을 고친다 |
| `상태: 대상 n/m 활성 …` | 15분마다(`heartbeat_seconds`) 나오는 생존 신호 |
| `... 초 동안 성공 응답이 없습니다` | 수집 중단 감지. 네트워크·provider 장애를 확인한다 |
| `슬롯 N개를 건너뜁니다` | 절전·중단으로 공백이 생겼다. N × 주기만큼이 손실이다 |
| `일일 상한 도달` | 그 풀은 운행일이 바뀔 때까지 멈춘다. 정상 동작이다 |
| `재시도 무의미 업무오류 … 당일 중단` | 권한·설정 문제다. 즉시 확인해야 한다 |

### 하루 뒤 확인

```bash
# 운행일 디렉터리의 원문·메타 페어 개수
for d in data/bronze/*/service_date=$(date +%F); do echo "$d : $(ls "$d" | wc -l)"; done

# 당일 quota 사용량
cat data/quota_ledger.json
```

배분안 A(지하철 위치 3노선 × 300초, 버스 2종 × 120초) 기준 기대값:

| 대상 | 원문+메타 파일 수 | 호출 |
|---|---:|---:|
| `subway_position` (3노선 합산) | 약 1,728 | 864 |
| `bus_position` | 약 1,440 | 720 |
| `bus_arrival_all` | 약 1,440 | 720 |

지하철 합산 호출이 950을 넘지 않아야 한다. 넘었다면 프로세스가 두 개 떠 있었다는
뜻이다.

## 대상 변경

`collector/targets.toml`을 고치고 프로세스를 재시작한다. 설정은 기동 시에만 읽는다.

현재 대상 노선·정류장은 **잠정값**이다. Route A 경로가 확정되면 교체한다.
`enabled = false`로 둔 항목은 기동 시 계획 로그에도 나오지 않는다.

`OA-15799`(일괄 도착정보)는 2026-08-26 실호출에서 `ERROR-340`이 확인돼 비활성
상태다. 활용사례 갤러리 등록 등으로 권한이 열리면 `enabled = true`로 바꾸고
지하철 예산을 배분안 C로 재계산한다.
