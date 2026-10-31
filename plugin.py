"""SnowLuma STT 插件 — 将入站 QQ 语音消息转换为文字。

通过 HookHandler 监听 chat.receive.before_process 事件，在消息到达 LLM 处理前
拦截语音消息段，调用 SnowLuma / OneBot 官方原生 fetch_ptt_text 接口转录，
将识别结果原地替换为文本段并重建 processed_plain_text。

原生官方方案：免去外部云模型和本地 sidecar 容器，直接复用官方语音转文字能力。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from maibot_sdk import HomeCard, HookHandler, MaiBotPlugin
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder

from .core.config import VoiceSttPluginConfig
from .core.stt_client import HealthCheckResult, SnowLumaSttClient, TranscriptionResult


class VoiceSttPlugin(MaiBotPlugin):
    """SnowLuma 语音转文字插件主类。"""

    config_model = VoiceSttPluginConfig

    _MAX_CONSECUTIVE_FAIL_LOG = 3  # 连续失败达到此阈值时记录 WARNING

    def __init__(self) -> None:
        super().__init__()
        self._client: SnowLumaSttClient | None = None
        self._stats: dict[str, int] = {}
        self._started_at: float = 0.0
        self._last_error_type: str | None = None
        self._reset_stats()

    def _reset_stats(self) -> None:
        self._stats = {
            "total_requests": 0,
            "total_success": 0,
            "total_failure": 0,
            "consecutive_failures": 0,
        }
        self._started_at = time.time()
        self._last_error_type = None

    # ===== 生命周期 =====

    async def on_load(self) -> None:
        self._init_client()
        self._reset_stats()
        self.ctx.logger.info(
            "SnowLuma STT 插件已加载，对接官方原生 fetch_ptt_text 接口"
        )

    async def on_unload(self) -> None:
        self._client = None
        self.ctx.logger.info("SnowLuma STT 插件已卸载")

    async def on_config_update(
        self, scope: str, config_data: dict, version: str
    ) -> None:
        if scope == "self":
            self._init_client()
            self.ctx.logger.info("SnowLuma STT 配置已更新 (version=%s)", version)

    # ===== 内部方法 =====

    def _init_client(self) -> None:
        if self.config.plugin.enabled:
            self._client = SnowLumaSttClient(
                ctx=self.ctx,
                timeout=self.config.stt.timeout_seconds,
                max_retries=self.config.stt.max_retries,
                retry_interval=self.config.stt.retry_interval,
                adapter_namespace=self.config.stt.adapter_namespace,
            )
        else:
            self._client = None

    def _record_transcription(self, result: TranscriptionResult) -> None:
        self._stats["total_requests"] += 1
        if result.success:
            self._stats["total_success"] += 1
            self._stats["consecutive_failures"] = 0
            self._last_error_type = None
        else:
            self._stats["total_failure"] += 1
            self._stats["consecutive_failures"] += 1
            self._last_error_type = result.error_type or "unknown"
            if self._stats["consecutive_failures"] == self._MAX_CONSECUTIVE_FAIL_LOG:
                self.ctx.logger.warning(
                    "SnowLuma STT 连续失败 %d 次 (原因: %s)",
                    self._stats["consecutive_failures"],
                    result.error_type,
                )

    def _uptime_hours(self) -> float:
        return (time.time() - self._started_at) / 3600.0

    async def _check_service_health(self) -> HealthCheckResult:
        if not self._client:
            return HealthCheckResult.fail("disabled", "disabled")
        return await self._client.check_health()

    # ===== 消息拦截钩子 =====

    @HookHandler(
        "chat.receive.before_process",
        name="snowluma_stt_transcriber",
        description="将入站语音消息段转录为文字",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        timeout_ms=30000,
        error_policy=ErrorPolicy.SKIP,
    )
    async def transcribe_voice_segments(
        self, message: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any] | None:
        """拦截入站消息，提取 message_id 并通过 fetch_ptt_text 将 voice 段转录为 text 段。"""
        if not self._client or not message:
            return None
        raw = message.get("raw_message")
        if not isinstance(raw, list):
            return None

        # 检查是否包含语音消息段
        voice_segments = [
            seg for seg in raw if isinstance(seg, dict) and seg.get("type") == "voice"
        ]
        if not voice_segments:
            return None

        message_id = message.get("message_id")
        if message_id is None or str(message_id).strip() == "":
            self.ctx.logger.warning("SnowLuma STT 跳过语音消息: 入站消息缺少 message_id")
            return None

        # 调用 SnowLuma 官方 fetch_ptt_text 原生接口
        result = await self._client.transcribe(message_id)
        self._record_transcription(result)

        if result.success and result.text and result.text.strip():
            voice_text = f"[语音: {result.text.strip()}]"
            self.ctx.logger.info(
                "SnowLuma STT 转写成功: message_id=%s 文本长度=%d 识别文本=%s",
                message_id,
                len(result.text.strip()),
                result.text.strip()[:60],
            )
        elif result.error_type == "empty_text" or (result.success and not result.text):
            voice_text = "[语音: 无法识别到内容]"
            self.ctx.logger.info("SnowLuma STT 识别成功但无内容: message_id=%s", message_id)
        else:
            voice_text = "[语音: 无法识别到文字]"
            self.ctx.logger.warning(
                "SnowLuma STT 识别失败: message_id=%s error=%s attempt=%d",
                message_id,
                result.error_type,
                result.attempt,
            )

        # 原地替换所有语音段为转写文本或提示标签
        for seg in voice_segments:
            seg.clear()
            seg["type"] = "text"
            seg["data"] = voice_text

        rebuilt_text = rebuild_plain_text(raw)
        message["processed_plain_text"] = rebuilt_text
        message["display_message"] = rebuilt_text
        return {"action": "continue", "modified_kwargs": {"message": message}}

    # ===== 状态卡片展示 =====

    @HomeCard(
        name="voice_stt_status",
        title="语音转文字状态",
        description="SnowLuma 官方语音转文字运行状态与统计",
        content="查看插件启用状态、接口可用性与转写统计。",
        icon="U0001F399",
        link_url="/plugin-config?plugin=wenaixi.mai_voice_speech_to_text",
        link_label="插件配置",
        width="medium",
        order=100,
    )
    async def stt_home_card(self) -> dict[str, Any]:
        s = self._stats
        enabled = "启用" if self._client else "已禁用"
        if self._client:
            health = await self._check_service_health()
            service_status = (
                health.status if health.ok else f"{health.status}/{health.error_type}"
            )
        else:
            service_status = "未启用"
        uptime_h = self._uptime_hours()
        rate_str = ""
        if s["total_requests"] > 0:
            rate = s["total_success"] / s["total_requests"] * 100
            rate_str = f"{rate:.1f}%"
        else:
            rate_str = "N/A"

        return {
            "blocks": [
                {
                    "type": "key_value",
                    "entries": {
                        "插件状态": enabled,
                        "接口健康": service_status,
                        "驱动方式": "SnowLuma 官方 fetch_ptt_text",
                        "运行时间": f"{uptime_h:.1f}h",
                        "总请求数": str(s["total_requests"]),
                        "识别成功率": rate_str,
                        "连续失败": str(s["consecutive_failures"]),
                        "最近错误": self._last_error_type or "无",
                    },
                },
                {
                    "type": "list",
                    "items": [
                        "直连协议端: adapter.snowluma.action.call / adapter.napcat.action.call",
                        "原生动作: fetch_ptt_text（复用 QQ 官方原生语音识别能力，免外部 API）",
                    ],
                },
            ]
        }


def rebuild_plain_text(segments: list[dict[str, Any]]) -> str:
    """从段列表重建纯文本表示。

    与适配器入站解码器逻辑对齐，保证 LLM 收到的文本格式统一。
    """
    parts: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        t = seg.get("type", "")
        if t == "text":
            parts.append(str(seg.get("data", "")))
        elif t == "voice":
            transcribed = seg.get("data", "")
            if transcribed:
                parts.append(transcribed)
            else:
                parts.append("[voice]")
        elif t == "image":
            parts.append("[image]")
        elif t == "reply":
            parts.append("[reply]")
    text = "".join(parts).strip()
    return text or "[unsupported]"


# 向后兼容导出别名
SenseVoiceSttPlugin = VoiceSttPlugin


def create_plugin() -> VoiceSttPlugin:
    """MaiBot 插件入口工厂函数（SDK 规范强制要求）。"""
    return VoiceSttPlugin()
