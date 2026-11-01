"""SnowLuma STT 语音转文字插件配置模型。"""

from maibot_sdk import Field, PluginConfigBase


class PluginSection(PluginConfigBase):
    """插件基础配置，对应 config.toml 的 [plugin] 节。"""

    __ui_label__ = "插件设置"
    __ui_icon__ = "settings"
    __ui_order__ = 0

    enabled: bool = Field(
        default=True,
        description="是否启用语音转文字",
        json_schema_extra={"group": "plugin"},
    )
    config_version: str = Field(
        default="0.2.0",
        description="配置版本",
        json_schema_extra={"group": "plugin"},
    )


class SttConfig(PluginConfigBase):
    """STT 后端配置，调用 SnowLuma 官方 fetch_ptt_text 接口。"""

    __ui_label__ = "SnowLuma 语音设置"
    __ui_icon__ = "record_voice_over"
    __ui_order__ = 10

    timeout_seconds: int = Field(
        default=25,
        description="单次语音识别总超时时间（秒，建议设为 25 秒以匹配底层 20 秒转写推送窗口）",
        json_schema_extra={"placeholder": "25", "group": "stt"},
    )
    initial_delay: float = Field(
        default=1.2,
        description="语音接收后的首枪缓冲等待时间（秒），给 QQ 落地与腾讯云端留出转录窗口",
        json_schema_extra={"placeholder": "1.2", "group": "stt"},
    )
    max_retries: int = Field(
        default=3,
        description="语音识别轮询重试最大次数（针对异步转写）",
        json_schema_extra={"placeholder": "3", "group": "stt"},
    )
    retry_interval: float = Field(
        default=1.0,
        description="语音识别轮询间隔时间（秒）",
        json_schema_extra={"placeholder": "1.0", "group": "stt"},
    )
    adapter_namespace: str = Field(
        default="auto",
        description="适配器命名空间（auto: 自动检测；或指定 adapter.snowluma / adapter.napcat）",
        json_schema_extra={"placeholder": "auto", "group": "stt"},
    )


class VoiceSttPluginConfig(PluginConfigBase):
    """插件根配置。"""

    plugin: PluginSection = Field(default_factory=PluginSection)
    stt: SttConfig = Field(default_factory=SttConfig)


# 保持向后兼容导出别名
SenseVoiceSttPluginConfig = VoiceSttPluginConfig