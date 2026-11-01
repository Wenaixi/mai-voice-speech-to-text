# 更新日志 (CHANGELOG)

## [v0.2.0] - 2026-11-02

### 官方原生 fetch_ptt_text 重构 (Major Architecture Update)
- **零外部模型依赖**：彻底摒弃外部繁重的 SenseVoice / Whisper Sidecar 容器架构，全量切换为基于 SnowLuma / OneBot 官方原生 `fetch_ptt_text` 接口，识别准确率与手机 QQ 原生转写 100% 对齐；
- **零磁盘 I/O 极速转写**：直接根据 `message_id` 原生异步拉取文本，不生成任何本地临时音频文件，极大降低磁盘与内存开销；
- **异步轮询与稳定性增强**：针对腾讯云 ASR 网络微延迟，注入 1.2s 初始延迟并放宽总超时至 25s，具备完备的轮询重试机制；
- **失败与降级标签语义化**：区分空音频与转写超时失败，回落结构清晰明了；
- **全域安全规范**：标准化 `.gitignore`，严格剔除并永久忽略 `CLAUDE.md` 与本地配置文件。
