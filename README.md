# 麦麦 QQ 语音实时转写文字插件

基于 SnowLuma / OneBot 官方原生 `fetch_ptt_text` 接口的入站语音转文字插件。

## 核心特性

- 官方原生：直接复用 QQ 官方客户端的原生语音识别结果，识别准确率与手机 QQ 保持完全一致；
- 零外部依赖：无需部署 SenseVoice、Whisper 等繁重模型，无需申请第三方云 API 或配置 API Key；
- 零本地磁盘 I/O：直接根据 `message_id` 异步请求识别结果，不生成任何本地临时音频文件；
- 容灾与异步轮询：自动兼容 SnowLuma 与 NapCat 命名空间，对服务端异步转写过程提供自动重试轮询。

## 配置说明

配置文件位于 `config.toml`：

```toml
[plugin]
enabled = true
config_version = "0.2.0"

[stt]
timeout_seconds = 15     # 单次识别请求超时（秒）
max_retries = 3          # 异步识别轮询最大重试次数
retry_interval = 1.0     # 轮询重试等待间隔（秒）
adapter_namespace = "auto" # 适配器命名空间 (auto / adapter.snowluma / adapter.napcat)
```

## 工作机制

1. 插件注册 `@HookHandler("chat.receive.before_process")` 拦截入站消息；
2. 检测到消息段包含 `voice` 时，提取消息的 `message_id`；
3. 通过适配器 API 总线发送动作 `fetch_ptt_text`；
4. 识别成功后，原地将 `voice` 消息段替换为文本段 `[voice]{识别文本}`，并同步更新 `processed_plain_text` 和 `display_message`；
5. 大模型核心直接接收到带语音文字的消息内容并进行语义理解与回复。
