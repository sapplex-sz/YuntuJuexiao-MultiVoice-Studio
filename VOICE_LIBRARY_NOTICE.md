# 音色库来源与许可说明

云途觉晓多人云音创作平台的运行时音色库包含两类内容：管理员安装的开源内置音色，以及用户自行上传并确认获得授权的“我的音色”。运行时音频存放在 `voice_library_data/`，不随 Git 仓库分发。

## AISHELL-3 内置音色

- 数据集：AISHELL-3（OpenSLR SLR93）
- 发布者：Beijing Shell Shell Technology Co., Ltd.
- 官方资源页：https://www.openslr.org/93/
- 论文：Yao Shi, Hui Bu, Xin Xu, Shaoji Zhang, Ming Li, *AISHELL-3: A Multi-speaker Mandarin TTS Corpus and the Baselines*
- 数据集许可证：Apache License 2.0
- 原始规模：约 85 小时、88,035 条语音、218 位普通话说话人

安装器 `scripts/install_builtin_voices.py` 仅选择 30 位匿名说话人的少量测试集片段，并把同一说话人的短句合并成便于参考音色使用的 WAV。平台保留原说话人编号、年龄段、性别、口音、逐句原文、来源链接和许可证字段。除拼接、转为单声道 PCM WAV 以及添加短静音间隔外，不对原始声音作风格化处理。

Apache License 2.0 全文见仓库根目录 [LICENSE](./LICENSE)。使用者仍需自行遵守适用的声音权益、人格权、隐私、数据保护、消费者保护及 AI 合成内容标识规则。不得暗示 AISHELL、OpenSLR 或原说话人对生成内容、平台或使用者提供背书。

## 用户保存的音色

保存个人音色前，界面要求用户确认拥有相应使用授权。该确认会记录在本地音色索引中，但平台无法替代权利审核。请勿保存来源不明、未经许可或可用于冒充他人的声音。
