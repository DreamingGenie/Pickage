# 실시간 교통 데이터 수집기 (collector)

## 이게 뭔가요

서울 지하철과 버스의 **실시간 위치·도착 정보를 계속 받아서 파일로 쌓아두는 프로그램**입니다.
공공데이터 API를 정해진 간격으로 호출하고, 받은 응답을 **하나도 가공하지 않고 원본 그대로**
저장합니다. 나중에 이 원본을 분석해서 "언제 출발하면 몇 시에 도착할지" 같은 걸 계산하는 데
쓸 재료입니다.

가장 중요한 성질이 하나 있습니다. **실시간 데이터는 지나가면 다시 받을 수 없습니다.**
과거 조회 기능이 없어서, 오늘 못 받은 오늘치는 내일이 되어도 받을 방법이 없습니다.
그래서 이 수집기의 목표는 "멈추지 않고 계속 받는 것"입니다.

## 어떻게 켜고 끄나요

**켜기 (권장 — 자동 재시작 모드)** — 수집기가 예상 못한 이유로 죽어도 스스로 되살아나게
하려면 `--supervise` 옵션으로 켭니다. PowerShell에서:

```powershell
# 켜기 전에 반드시 중복 확인부터 (아래 "켜기 전 중복 확인" 참고)
Start-Process -FilePath "C:\git\S15P21A506\collector\scripts\run_collector.cmd" -ArgumentList "--supervise"
```

까만 창이 하나 뜨고 수집이 시작됩니다. 이 모드에서는 python이 죽으면 **60초 뒤 자동으로
다시 켜집니다.** 창은 **최소화**해서 두면 됩니다.

파일을 그냥 더블클릭해도 켜지지만, 그건 자동 재시작이 없는 단순 실행입니다. 계속 켜둘
용도면 위의 `--supervise`를 쓰세요.

**끄기 (자동 재시작 모드는 2단계)** — 자동 재시작 때문에 그냥 창만 닫으면 다시 살아납니다.
완전히 멈추려면:

```powershell
# 1) 재시작을 막는 정지 표시 파일 생성
New-Item -ItemType File "C:\git\S15P21A506\data\STOP_COLLECTOR" -Force
# 2) 그 까만 창에서 Ctrl + C  (또는 창을 닫는다)
```

다시 켤 때는 `data\STOP_COLLECTOR` 파일이 자동으로 지워지므로 신경 쓰지 않아도 됩니다.

> ⚠️ 컴퓨터를 껐다 켜거나 로그아웃하면 수집기도 꺼집니다. 다시 위 `--supervise` 명령으로 켜야 합니다.

### 켜기 전 중복 확인 (반드시)

**수집기는 한 번에 하나만** 떠 있어야 합니다(이유는 아래 규칙 1번). 켜기 전에 이미
떠 있는지 확인합니다. 자동 재시작 모드는 python이 죽고 되살아나는 **60초 공백**이 있는데,
그때 python만 세면 "0개"로 보여 오판할 수 있습니다. 그래서 **python이 아니라 감시자(cmd)를**
확인합니다.

```powershell
$sup = Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
       Where-Object { $_.CommandLine -like '*run_collector*' }
$py  = Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
       Where-Object { $_.CommandLine -like '*run_scheduler*' }
"감시자 cmd: $(@($sup).Count) / 수집 python: $(@($py).Count)"
```

- **감시자 cmd가 1개 이상이면 이미 돌고 있는 것** → 새로 켜지 마세요. (python이 0개여도
  60초 재시작 대기 중일 수 있습니다.)
- 감시자 cmd가 0개일 때만 새로 켭니다.

## 꼭 지켜야 하는 규칙 세 가지

1. **수집기는 한 번에 하나만 켜세요.** 두 개를 켜면 "오늘 몇 번 호출했는지" 기록이
   서로 엉켜서, 하루 호출 한도를 넘겨버리고 그날 수집이 통째로 막힙니다.

2. **노트북이 절전으로 들어가면 그만큼 데이터가 빕니다.** 절전 동안엔 프로그램이
   멈추기 때문입니다. 계속 받으려면 절전을 꺼두세요 (아래 "노트북 설정" 참고).

3. **키(비밀번호 같은 것)는 파일에만 넣고 어디에도 붙여넣지 마세요.** 채팅·메신저·
   커밋에 올리면 안 됩니다.

## 데이터는 어디에 쌓이나요

전부 `C:\git\S15P21A506\data\` 폴더 아래에 쌓입니다.

- `data\bronze\` — 받은 원본 데이터 (지하철/버스별, 날짜별 폴더)
- `data\logs\collector.log` — 수집기가 지금 뭘 하고 있는지 기록
- `data\quota_ledger.json` — 오늘 각 키로 몇 번 호출했는지 세는 장부

이 폴더는 **이 노트북에만 있고 다른 곳에 자동 백업되지 않습니다.** 노트북이 고장나면
그동안 모은 데이터가 사라지니, 가끔 외장하드나 다른 곳에 복사해두는 게 좋습니다.

## 잘 돌고 있는지 확인하는 법

로그 파일을 보면 됩니다. (PowerShell에서는 `tail`이 없으니 `Get-Content -Tail`을 씁니다.)

```powershell
Get-Content "C:\git\S15P21A506\data\logs\collector.log" -Tail 30
```

15초쯤 뒤 `OK` 줄이 새로 찍히면 정상입니다. 그리고 위 "켜기 전 중복 확인" 명령을 다시
돌려 **감시자 cmd가 정확히 1개**인지 확인합니다(python은 0~1개일 수 있음 — 재시작 공백).

- 15분마다 `상태: 대상 …` 줄이 나오면 정상입니다.
- `OK` 가 많으면 잘 받고 있는 겁니다.
- `슬롯 N개를 건너뜁니다` 가 보이면 절전 등으로 잠깐 멈췄던 흔적입니다.

오늘 얼마나 모았는지 요약해서 보려면:

```bash
python -m collector.export_bronze --summary
```

## 데이터를 꺼내려면

하루치를 압축 파일 하나로 묶어서 내보낼 수 있습니다 (원본은 그대로 남습니다).

```bash
python -m collector.export_bronze              # 오늘치를 zip으로
python -m collector.export_bronze --all        # 전체 날짜
```

`data\exports\` 폴더에 `bronze_날짜.zip` 으로 나옵니다.

## 키(인증키) 관리

각 API를 부르려면 인증키가 필요합니다. 키는 `collector\.env.local` 파일에 적어둡니다.
이 파일은 일부러 Git에 올라가지 않게 되어 있어서, **다른 노트북에서 새로 시작하면
이 파일을 직접 다시 만들어야** 합니다. 채우는 형식은 `collector\.env.example` 를 참고하세요.

- 팀원 키를 함께 쓰면 하루 받을 수 있는 양이 그만큼 늘어납니다. `..._2`, `..._3` 처럼
  번호를 붙여 추가합니다. **번호는 건너뛰지 말고 순서대로** 채우세요.
- 키를 새로 넣거나 바꾼 뒤에는 수집기를 껐다 켜야 반영됩니다.

## 무엇을 얼마나 받고 있나

받을 대상과 간격은 `collector\targets.toml` 파일에서 정합니다. **코드를 고치지 않고
이 파일만 바꾸면** 노선이나 간격을 조정할 수 있습니다. 바꾼 뒤엔 수집기를 재시작하세요.

지금 받고 있는 것 (2026-08-27 기준):
- 지하철 1~9호선 위치, 지하철 전체 도착정보
- 버스 승차 인원이 많은 상위 40개 노선의 위치·도착정보

버스 노선을 더 늘리고 싶으면, 승차 순위대로 다음 노선을 뽑아주는 도구가 있습니다:

```bash
python -m collector.gen_bus_targets --interval 60
```

## 노트북 설정 (계속 켜둘 경우)

절전으로 들어가면 데이터가 비므로, 계속 받으려면 절전을 끕니다.
아래 명령을 **관리자 권한 PowerShell**에서 한 번 실행하세요 (시스템 설정 변경이라 직접 하세요).

```powershell
powercfg /change standby-timeout-ac 0    # 콘센트 연결 시 절전 안 함
powercfg /change monitor-timeout-ac 0    # 화면도 끄지 않으려면 (선택)
```

되돌리려면 `0` 대신 원래 분 단위 값(예: `30`)을 넣습니다.
화면 절전(monitor)은 꺼져도 수집엔 영향 없으니 그대로 둬도 됩니다. **시스템 절전(standby)만**
끄면 됩니다. 노트북 덮개를 닫아도 절전되지 않게 하려면 Windows 전원 설정에서
"덮개를 닫으면: 아무 것도 안 함"으로 바꾸세요.

## 백신(V3)이 수집기를 끄는 경우

AhnLab V3가 수집기를 악성코드로 오해해 끄는 일이 있었습니다. 지금 방식(창을 띄우고 직접
실행)으로 대부분 해결됐지만, 또 막히면 V3에서 이 폴더를 예외로 등록하면 됩니다.
자세한 내용은 [`../docs/트러블슈팅_V3_수집기_중지_260827.md`](../docs/트러블슈팅_V3_수집기_중지_260827.md)
를 보세요.

---

## (개발자용) 구조와 테스트

- `common/` — provider와 무관한 공통 부품 (호출·저장·quota·스케줄러 등)
- `sources/` — API별 어댑터 (지하철·버스). 새 API는 여기에 모듈 하나 + `registry.py`에 한 줄
- `run_scheduler.py` — 상시 수집 실행 (지금 도는 것)
- `run_collector.py` — 1회 수동 수집 (디버깅용)
- `export_bronze.py` — 데이터 내보내기
- `targets.toml` / `.env.local` — 설정 / 키

자세한 설계는 [`BRONZE_CONTRACT.md`](BRONZE_CONTRACT.md)(저장 규약)와
[`OPERATIONS.md`](OPERATIONS.md)(운영 상세), 상위 [`../docs/DATA_PLATFORM_PLAN_260826.md`](../docs/DATA_PLATFORM_PLAN_260826.md)를 참고하세요.

테스트 (네트워크·키 없이 실행됩니다):

```bash
python -m collector.smoke_test          # 전 경로 스모크 (53건)
python collector/tests/test_scheduler.py # 스케줄러 로직 (18건)
python collector/tests/test_ledger.py    # 원장·복구 (19건)
python collector/tests/test_config.py    # 설정·rotation·키별 한도 (18건)
```
