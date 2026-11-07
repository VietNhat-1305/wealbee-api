@echo off
rem Chay 1 lan: tao lich Windows quet Wealbee API moi gio tu may nay (chay an, khong hien cua so).
schtasks /Create /TN "WealbeeAPI_QuetMayVN" /SC HOURLY /MO 1 /ST 00:37 /TR "wscript.exe //B //Nologo \"%~dp0chay_may.vbs\"" /F
echo Da tao lich. Xoa lich: schtasks /Delete /TN "WealbeeAPI_QuetMayVN" /F
pause
