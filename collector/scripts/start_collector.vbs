' ============================================================================
'  수집기 감시 루프를 콘솔 창 없이 백그라운드로 띄운다.
'
'  cmd 를 직접 시작프로그램에 넣으면 검은 창이 계속 떠 있어 실사용이 불편하다.
'  WScript.Shell.Run 의 세 번째 인자(창 스타일 0 = 숨김)로 창을 없앤다.
'  네 번째 인자 False 는 "끝날 때까지 기다리지 않음" 이다. 감시 루프는 하루
'  종일 돌기 때문에 기다리면 로그온이 멈춘다.
'
'  이 파일을 시작프로그램 폴더에 복사하지 말고, 그쪽에 이 파일을 가리키는
'  래퍼 vbs 를 두는 편이 낫다. 저장소를 업데이트하면 자동으로 반영된다.
'    시작프로그램: shell:startup
' ============================================================================

Option Explicit

Dim shell, fso, here, target
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)
target = here & "\run_collector_bg.cmd"

If Not fso.FileExists(target) Then
    ' 조용히 실패하면 원인을 찾기 어렵다. 로그온 시 한 번만 뜨는 알림이므로 감수한다.
    MsgBox "수집기 스크립트를 찾을 수 없습니다:" & vbCrLf & target, 16, "JR-Collector"
    WScript.Quit 1
End If

shell.Run """" & target & """", 0, False
