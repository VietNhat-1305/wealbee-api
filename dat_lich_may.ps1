# Lich Windows: quet hieu suat Wealbee API tu may o Viet Nam.
# Chay khi dang nhap Windows + moi gio khi may bat; lo luot (may tat / ngu) thi chay bu khi may mo lai. Chay an (wscript).
$ten = "WealbeeAPI_QuetMayVN"
$vbs = Join-Path $PSScriptRoot "chay_may.vbs"
$hanhDong = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//B //Nologo `"$vbs`"" -WorkingDirectory $PSScriptRoot
$khiDangNhap = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$moiGio = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(37) -RepetitionInterval (New-TimeSpan -Hours 1)
$caiDat = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $ten -Action $hanhDong -Trigger @($khiDangNhap, $moiGio) -Settings $caiDat `
    -Description "Quet hieu suat Wealbee API tu may o Viet Nam (repo VietNhat-1305/wealbee-api)" -Force | Out-Null
Get-ScheduledTask -TaskName $ten | Select-Object TaskName, State
Write-Output "Xoa lich: Unregister-ScheduledTask -TaskName $ten -Confirm:`$false"
