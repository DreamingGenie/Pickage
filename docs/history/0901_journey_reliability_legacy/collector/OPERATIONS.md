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
# 가상환경이 없으면 `which python3` 결과(예: /usr/bin/python3)를 그대로 쓴다.
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

### Windows 노트북 — 포그라운드 실행 (V3 ASD 대응)

이 장비에는 **AhnLab V3 Internet Security**가 있고, 행위기반 진단(ASD)이 다음 패턴을
악성코드로 보고 수집 프로세스를 중지시킨다(2026-08-26 실제 발생).

```
시작프로그램 .vbs → 숨김 cmd.exe → 자식 python 이 주기적으로 외부 네트워크 호출
```

이건 WSH 드로퍼 + 지속성 확보 + 비컨의 전형적 패턴이라 ASD 가 잡는 게 정상이다.
숨기는 기술로 우회하면 V3 와 계속 싸우게 되므로, **탐지 신호 자체를 없앤다.** 즉
창을 숨기지 않고, wscript 로 감싸지 않고, 자동시작에 등록하지 않는다. 사용자가 직접
연 보이는 터미널의 자식 프로세스는 ASD 가 거의 건드리지 않는다.

```
collector/scripts/run_collector.cmd            보이는 창에서 1회 구동
collector/scripts/run_collector.cmd --supervise 죽으면 60초 뒤 재시작(창은 계속 보임)
```

실행은 파일 더블클릭 또는 터미널에서 한다. 창을 최소화해 두면 된다. 정지는 그 창에서
`Ctrl+C`(진행 중 호출을 마치고 종료). 파이썬 경로가 PATH 에 없으면 `set JR_PYTHON=<절대경로>`
를 먼저 준다.

배치 파일은 **ASCII 로만** 작성한다. cmd.exe 가 배치를 OEM 코드페이지(cp949)로 읽어
UTF-8 한글이 명령으로 잘못 파싱되기 때문이다. 사용자용 한글 메시지는 파이썬 로그에 있다.

### V3 (AhnLab) 예외 등록 — 근본 해결

주기적 외부 호출은 성격상 없앨 수 없다. 포그라운드 실행으로 탐지 확률을 크게 낮추지만,
ASD 가 다시 반응하면 **이 폴더를 V3 예외에 넣는 것이 근본 해결**이다.

예외 등록은 보안 설정 변경이므로 **사용자가 직접 한다.** 대략의 경로는 다음과 같다(9.0 기준,
버전에 따라 메뉴명이 다를 수 있다).

1. V3 메인 창 → **환경설정**(톱니바퀴) → **PC 보안** → **검사 예외 설정**(또는 **예외 폴더/파일**)
2. 폴더 예외에 `C:\git\S15P21A506` 추가 (또는 파이썬 경로
   `C:\Users\<사용자>\AppData\Local\Programs\Python\Python312\` 추가)
3. ASD(행위기반 진단)에 별도 예외 항목이 있으면 같은 경로를 그쪽에도 추가
4. 이미 격리(치료)된 항목이 있으면 **격리소**에서 복원

예외를 넣은 뒤에는 어떤 실행 방식이든 안전해지므로, 그때 자동시작(아래)을 붙여도 된다.
회사 지급 장비라 예외 등록이 정책상 막혀 있으면 IT 담당에게 이 수집기 용도를 설명하고
요청한다.

### (예외 등록 후) 자동시작 — 최소화 창 바로가기

V3 예외를 넣은 뒤에야 쓴다. 시작프로그램 폴더에 `run_collector.cmd --supervise` 를 가리키는
**바로가기(.lnk)** 를 두고 실행 속성을 "최소화"로 둔다. 숨김이 아니라 최소화이므로 ASD
신호가 약하다. 관리자 승격이 필요 없다.

```powershell
$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$startup\JR-Collector.lnk")
$lnk.TargetPath = "$env:SystemRoot\System32\cmd.exe"
$lnk.Arguments  = '/c "C:\git\S15P21A506\collector\scripts\run_collector.cmd" --supervise'
$lnk.WorkingDirectory = "C:\git\S15P21A506"
$lnk.WindowStyle = 7   # 7 = 최소화
$lnk.Save()
```

제거는 시작프로그램 폴더의 `JR-Collector.lnk` 를 지운다. 정지는 창에서 `Ctrl+C`.

### 참고 — Linux/서버라면 작업 스케줄러 대신

`Register-ScheduledTask`와 `schtasks /create`는 관리자 승격을 요구한다(승격 없이 실행하면
`Access is denied` / `HRESULT 0x80070005`). 승격이 되는 서버라면 작업 스케줄러가 놓친 실행
보정과 절전 복귀 재시작까지 해주지만, 이 노트북 시나리오에서는 위 포그라운드 방식을 쓴다.

### 절전이 곧 수집 공백이다

노트북에서 가장 큰 손실 원인이다. 현재 설정은 `powercfg`로 확인한다.

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
```

`현재 AC 전원 설정 색인`이 `0x00000708`이면 1800초(30분) 유휴 시 절전이다. 그 상태로
방치하면 30분마다 수집이 멈춘다. 상시 수집이 목적이면 AC 전원에서 절전을 끈다.

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

이 명령은 시스템 전원 설정을 바꾸므로 **직접 실행해 판단하고 적용한다.** 되돌릴 때는
`0` 대신 원래 분 단위 값(예: `30`)을 넣는다.

절전으로 생긴 공백은 로그의 `슬롯 N개를 건너뜁니다`로 확인할 수 있다. `N × 주기`만큼이
영구 손실이다.

복귀하면 수집기가 스스로 다음 슬롯부터 이어간다. 놓친 슬롯을 몰아서 호출하지는
않는다 — 실시간 데이터는 지나간 시점을 받을 수 없어 따라잡기가 무의미하고 quota만
태운다.

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

## 수집 데이터 꺼내기

운행일 단위로 원문·메타를 묶어 내보낸다. 원본은 지우지 않는다(복사다).

```bash
# 오늘 수집 현황만 확인 (묶지 않음)
python -m collector.export_bronze --summary

# 오늘 운행일을 zip으로
python -m collector.export_bronze

# 특정 운행일 / 전체 운행일
python -m collector.export_bronze --service-date 2026-08-27
python -m collector.export_bronze --all
```

산출물은 `data/exports/bronze_<운행일>.zip`이고 안에 `MANIFEST.json`이 들어간다.
XML/JSON은 압축률이 높아 실측 **8% 수준**으로 줄어든다(187MB/일 → 약 15MB).

**묶기 전에 원문의 sha256을 메타 기록값과 대조한다.** 불일치가 있으면 매니페스트에
남기고 종료 코드 1을 반환하되 묶기는 계속한다 — 손상된 파일도 증거다. 실시간
데이터는 다시 받을 수 없으므로 손상 사실을 늦게 아는 것이 가장 나쁘다.

매니페스트의 `key_ids`에 `sample`이 있으면 샘플키 응답이 섞여 있다는 뜻이다. 샘플키는
반환 행 수가 제한된 잘린 데이터이므로 Silver로 넘기면 안 된다. 요약 출력에서도 경고한다.

## quota 원장이 깨졌을 때

`data/quota_ledger.json`은 그날 몇 번 호출했는지를 담은 유일한 근거다. 이 값이
0으로 돌아가면 수집기는 일일 상한을 인식하지 못하고 그날 예산을 모두 태운다.
그래서 **읽기에 실패했을 때 조용히 0으로 리셋하지 않는다.**

| 상황 | 동작 |
|---|---|
| 파일 없음 + 당일 Bronze도 없음 | 첫 실행으로 보고 빈 원장으로 시작한다 |
| 파일 없음 + 당일 Bronze에 기록 있음 | 원장 유실로 보고 Bronze에서 복원하며 경고한다 |
| 파일 손상 | 깨진 파일을 `ledger.json.corrupt.<UTC>`로 **보존**하고 Bronze에서 복원한다 |
| 파일 손상 + 복원 근거 없음 | `LedgerCorrupted`로 **기동을 중단**한다 |

복원값은 `bronze-v2` 이후 메타의 `quota_pool`·`key_id`로 재구성하며 **하한**이다.
호출은 했으나 저장에 실패한 건은 셀 수 없다. 복원이 일어난 날은 상한에 여유를
두고 운영한다.

마지막 줄, 즉 기동이 중단되는 경우의 대처는 이렇다. 로그에 이유가 남으므로 먼저
읽고, **오늘 호출이 실제로 없었던 것이 확실할 때만** 원장을 지운다.

```bash
cat data/quota_ledger.json.corrupt.* 2>/dev/null | head
ls data/bronze/*/service_date=$(date +%F)/ 2>/dev/null | head
```

당일 Bronze에 기록이 있는데 복원이 안 됐다면 그 기록이 `bronze-v1`(구 스키마)이라
`quota_pool`·`key_id`가 없다는 뜻이다. 그 경우 메타 파일 수를 직접 세어 원장을
손으로 만드는 편이 안전하다. 0으로 두고 재시작하면 안 된다.

## 대상 변경

`collector/targets.toml`을 고치고 프로세스를 재시작한다. 설정은 기동 시에만 읽는다.

현재 대상 노선·정류장은 **잠정값**이다. Route A 경로가 확정되면 교체한다.
`enabled = false`로 둔 항목은 기동 시 계획 로그에도 나오지 않는다.

`OA-15799`(일괄 도착정보)는 2026-08-26 실호출에서 `ERROR-340`이 확인돼 비활성
상태다. 활용사례 갤러리 등록 등으로 권한이 열리면 `enabled = true`로 바꾸고
지하철 예산을 배분안 C로 재계산한다.
