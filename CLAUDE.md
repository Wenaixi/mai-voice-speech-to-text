# CLAUDE.md - SnowLuma 语音转文字插件 (wenaixi_mai_voice_speech_to_text)

## 1. 模块定位与系统职责
- 插件标识符：wenaixi.mai_voice_speech_to_text
- 当前生效版本：v0.2.0
- 托管仓库：[Wenaixi/mai-voice-speech-to-text](https://github.com/Wenaixi/mai-voice-speech-to-text)
- 核心定位：监听入站 QQ 消息中的语音段 (voice)，通过 SnowLuma / OneBot 官方原生的 fetch_ptt_text 接口直接获取 QQ 官方语音识别文本，原地替换消息段并重建纯文本供大模型阅读。

## 2. 关键工程规范与核心架构
- 零外部依赖：彻底剥离 SenseVoice 独立 sidecar 容器及第三方云端 ASR 接口，免去 API Key 与模型部署成本；
- 零本地磁盘 I/O：不再提取 Base64 转码本地 wav 临时文件，直接传递 message_id 由底层协议端完成原生识别；
- 适配器总线直连：优先通过 adapter.snowluma.action.call 调用底层动作，并自动兼容 fallback 至 adapter.napcat.action.call；
- 异步退避轮询：针对 QQ 原生服务端异步转写的延迟，内置可配置重试机制 (max_retries 与 retry_interval)，在文本未落地时自动平滑重试；
- 配置路径：config.toml（由 SDK 统一管理热更新）；
- 编码与规范：严格遵循 PEP 8，文档与注释一律不使用 emoji，杜绝虚假套话。

## 3. 历史版本与演进记录
- v0.2.0 (2026-11-01): 架构大升级，彻底废除 SenseVoice 本地/远程模型方案，全面切换为 SnowLuma 官方原生 fetch_ptt_text 接口，删除 audio_utils.py 与 sidecar/ 目录，提升稳定性并降低系统开销。
- v0.1.0: 初始版本，基于 SenseVoice sidecar 方案。
