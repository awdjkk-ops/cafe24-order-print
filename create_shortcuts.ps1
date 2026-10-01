# 바탕화면 아이콘을 '주문서 출력 관리' 하나로 정리
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
foreach ($old in @("주문서 지금 출력", "마지막 출력 다시 뽑기", "주문서 출력 설정")) {
    $p = Join-Path $desktop "$old.lnk"
    if (Test-Path $p) { Remove-Item $p -Force; Write-Host "  - 예전 아이콘 삭제: $old" }
}
$ws = New-Object -ComObject WScript.Shell
$l = $ws.CreateShortcut((Join-Path $desktop "주문서 출력 관리.lnk"))
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if ($pyw) {
    $l.TargetPath = $pyw
    $l.Arguments = '"' + (Join-Path $dir "order_manager.py") + '"'
} else {
    $l.TargetPath = Join-Path $dir "manager.bat"
    $l.WindowStyle = 7
}
$l.WorkingDirectory = $dir
$l.IconLocation = "$env:SystemRoot\System32\imageres.dll,46"
$l.Save()
Write-Host "  - 바탕화면에 '주문서 출력 관리' 아이콘을 만들었습니다."
