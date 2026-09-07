# 云途觉晓多人云音创作平台：Tesla V100 部署

本项目基于 OpenMOSS/MOSS-TTSD 的 `110e802`，面向 Windows / Linux 上的 Tesla V100，产品名称为“云途觉晓多人云音创作平台”。

## 必要修改

- 根据目标显卡的计算能力选择精度：V100 使用 FP16，Ampere 及更新显卡默认 BF16，CPU 默认 FP32。
- V100 使用 PyTorch SDPA；显式指定不支持的 BF16 或 FlashAttention 2 时给出清晰错误。网页与批处理共用同一套判断。
- 音频编解码器保持 FP32；可用 `--codec_device` 指定另一张卡，避免把编解码器的内部 FP32 计算误改成 FP16。
- 提供保留 `sm_70` 的 PyTorch 2.6.0 / CUDA 12.4 依赖组合。
- 网页完整推理流程禁用梯度；共享的编解码器按单任务排队，最多等待 8 个任务。
- 生成后检查空音频和非有限数值，避免把错误结果当成成功音频。

## Windows 安装

使用独立的 Python 3.11 或 3.12 环境：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-v100.txt
.venv\Scripts\python.exe scripts\download_models.py --root C:\AI\models
```

如果网络对大文件整段下载有问题，可使用带续传和 SHA-256 校验的替代下载器：

```powershell
.venv\Scripts\python.exe scripts\download_models_ranged.py --root C:\AI\models
```

在国内网络下可给分段下载器添加 `--weight-source modelscope`，使用 OpenMOSS 在 ModelScope 的官方权重镜像，仍以固定 Hugging Face 版本的 SHA-256 校验权重。

下载器固定了模型与编解码器的提交版本。不要在尚未验证兼容性的情况下自动更新权重、模型代码或依赖。

## 启动网页

```powershell
.venv\Scripts\python.exe gradio_demo.py --model_path C:\AI\models\MOSS-TTSD-v1.0 --codec_path C:\AI\models\MOSS-Audio-Tokenizer --device cuda:1 --codec_device cuda:0 --dtype float16 --attn_implementation sdpa --host 0.0.0.0 --port 7863
```

当前双 V100 服务器将主模型放在 `cuda:1`，音频编解码器放在 `cuda:0`。实测三组完整测试的峰值显存分别约为 15.76 GiB 和 6.94 GiB。单卡机器则将两个设备都改为 `cuda:0`；任务并行使用同一 GPU 时仍可能争抢显存。

本机部署入口脚本是 `C:\AI\MOSS-TTSD\scripts\start-windows.cmd`，模型目录是 `C:\AI\models`。该启动脚本使用本地权重离线运行，日志保存于 `C:\AI\MOSS-TTSD\service.log`。

## 使用

网页现默认使用简体中文。界面按「写台词 → 参考音色（可选）→ 试听作品」组织；高级参数默认折叠。点击「单人朗读」「双人对话」或「播客开场」可以加载中文示例，同时清空所有参考音频与原文，防止误用先前的音色。

在「对话台词」中输入带说话人标记的文本，例如：

```text
[S1]你好，欢迎来到我们的语音工作室。
[S2]你好，今天我们来测试中文对话生成。
```

点击「生成语音」，等待完成后在右侧播放器试听或下载。不上传参考音频即可生成对话。要使用指定声音，展开「参考音色」，给对应说话人上传参考音频；服务器自动转写并填写原文。核对人名、数字和漏字后即可生成，也可以直接手动修改原文。「生成长度上限」（`max_new_tokens`）不是固定输出时长；到达上限会截断生成。建议先用短文本验证音色和效果。

### 参考音频自动转文字

- 上传后自动识别，支持自动判断语言，也可指定中文或英语后点击「重新识别原文」。重新识别会覆盖原文；运行途中手动输入的文字会保留。
- 中文识别结果转换为简体。建议使用 5～30 秒的单人清晰录音，自动识别限制为 0.5～120 秒，不会偷偷截断音频。静音、超时或识别失败时会给出中文提示，可重试或手动填写。
- 五位说话人分别识别。更换、清空音频或加载示例时清空关联原文；过期识别结果不会写入新音频。请等识别完成再生成。
- 转写与语音生成共享串行任务队列。识别由独立子进程运行，完成或超时后释放显存，不常驻另一个大模型；所有音频均在服务器本地处理。

识别环境独立位于 `.venv-asr`，不修改原 `.venv` 的依赖。初次安装：

```powershell
.venv\Scripts\python.exe -m venv .venv-asr
.venv-asr\Scripts\python.exe -m pip install -r requirements-asr.txt
.venv-asr\Scripts\python.exe scripts\download_asr_model.py --output C:\AI\models\faster-whisper-large-v3-turbo
```

使用 faster-whisper 1.2.1 / CTranslate2 4.6.0，模型固定为 `mobiuslabsgmbh/faster-whisper-large-v3-turbo` 的 `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` 版本。运行时强制离线，不上传音频、不临时下载模型。Windows 子进程复用 `.venv/Lib/site-packages/torch/lib` 下已有 CUDA 12 / cuDNN 9 DLL，默认在 GPU 0 上使用 FP16。

可通过 `MOSS_ASR_MODEL`、`MOSS_ASR_PYTHON`、`MOSS_ASR_DEVICE`（`cuda` / `cpu`）、`MOSS_ASR_DEVICE_INDEX` 覆盖路径及设备。默认模型目录为项目同级 `models/faster-whisper-large-v3-turbo`，CPU 模式使用 INT8。`reference_asr.py` 负责调用与错误提示，`scripts/asr_worker.py` 负责识别；异常会在 `service.log` 中带 `[ASR]` 标记，不记录原文内容。

### 持久化音色库

上传音频并核对原文后，可在页面中命名保存；下次直接从“从音色库选择”列表使用。数据默认保存在 `C:\AI\MOSS-TTSD\voice_library_data`，服务重启不会丢失。建议定期备份该目录，也可在启动服务前通过 `YUNTU_VOICE_LIBRARY_DIR` 指定独立数据盘。

安装 30 个 AISHELL-3 开源中文音色：

```powershell
.venv\Scripts\python.exe scripts\install_builtin_voices.py --count 30
```

安装器支持已完成音色跳过、连接重试和重复执行。AISHELL-3 来源、转换方式与 Apache 2.0 许可说明见 `VOICE_LIBRARY_NOTICE.md`。

界面代码位于 `studio_ui.py`，推理与中文错误提示位于 `gradio_demo.py`。播放器、上传及加载提示使用随 Gradio 6.5.1 安装的简体中文语言包；升级 Gradio 后需要再次验证语言模块的导出接口。

## 批处理

```powershell
$env:CUDA_VISIBLE_DEVICES='1'
.venv\Scripts\python.exe inference.py --model_path C:\AI\models\MOSS-TTSD-v1.0 --codec_model_path C:\AI\models\MOSS-Audio-Tokenizer --input_jsonl examples\v100_zh.jsonl --save_dir outputs --mode generation --batch_size 1 --max_new_tokens 512 --text_normalize
```

批处理默认每张可见 GPU 各加载一个完整模型。`CUDA_VISIBLE_DEVICES` 会重新编号设备；设置为 `1` 后，进程内该设备名是 `cuda:0`。

批处理和独立测试需要先停止同卡的网页实例。运行需要两张卡的 ComfyUI 工作流前，也应先停止本服务释放显存。

## 检查

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\smoke_test_v100.py --model_path C:\AI\models\MOSS-TTSD-v1.0 --codec_path C:\AI\models\MOSS-Audio-Tokenizer --device cuda:1 --codec_device cuda:0
```

完整测试会生成中文单人语音、双人对话，并使用刚生成的单人语音验证参考音频编码与续说流程。结果写入 `output\verification`。运行完整测试前先停止占用相同 GPU 的本项目网页实例，避免重复加载。
