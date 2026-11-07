@echo off
rem Quet hieu suat Wealbee API tu may o Viet Nam (lich Windows moi gio). Chi day du lieu do cua may len GitHub.
cd /d %~dp0
set PYTHONIOENCODING=utf-8
git pull -q --rebase >> nhat_ky_may.log 2>&1
python -m wb_api.chay --nguon may-vn --khong-bao-cao >> nhat_ky_may.log 2>&1
git add data/do/may-vn >> nhat_ky_may.log 2>&1
git diff --cached --quiet && exit /b 0
git commit -q -m "Quet may VN %date% %time%" >> nhat_ky_may.log 2>&1
git push -q >> nhat_ky_may.log 2>&1 || (git pull -q --rebase && git push -q) >> nhat_ky_may.log 2>&1
