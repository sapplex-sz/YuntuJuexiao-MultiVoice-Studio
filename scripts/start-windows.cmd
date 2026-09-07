@echo off
setlocal
cd /d C:\AI\MOSS-TTSD
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
set OMP_NUM_THREADS=8
set HF_HOME=C:\AI\cache\moss-ttsd
set HF_HUB_OFFLINE=1
set GRADIO_ANALYTICS_ENABLED=False
if exist service.log move /Y service.log service.previous.log >nul
.venv\Scripts\python.exe -u gradio_demo.py --model_path C:\AI\models\MOSS-TTSD-v1.0 --codec_path C:\AI\models\MOSS-Audio-Tokenizer --device cuda:1 --codec_device cuda:0 --dtype float16 --attn_implementation sdpa --host 0.0.0.0 --port 7863 >> service.log 2>&1
exit /b %ERRORLEVEL%
