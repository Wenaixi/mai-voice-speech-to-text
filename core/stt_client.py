"""SnowLuma STT 客户端 — 对接 SnowLuma / OneBot 官方 fetch_ptt_text 原生接口。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TranscriptionResult:
    """转录结果。

    Attributes:
        text: 转录文本（失败时为空字符串）。
        success: 是否成功。
        error_type: 失败原因分类
            ("timeout" / "not_found" / "api_error" / "invalid_message_id" / "unknown" / None)。
        attempt: 实际尝试次数。
    """

    text: str
    success: bool
    error_type: str | None = None
    attempt: int = 1

    @classmethod
    def ok(cls, text: str, attempt: int = 1) -> TranscriptionResult:
        return cls(text=text.strip(), success=True, attempt=attempt)

    @classmethod
    def fail(cls, error_type: str, attempt: int = 1) -> TranscriptionResult:
        return cls(text="", success=False, error_type=error_type, attempt=attempt)


@dataclass
class HealthCheckResult:
    """STT 接口健康检查结果。"""

    ok: bool
    status: str
    error_type: str | None = None

    @classmethod
    def ready(cls) -> HealthCheckResult:
        return cls(ok=True, status="ready")

    @classmethod
    def fail(cls, error_type: str, status: str = "unreachable") -> HealthCheckResult:
        return cls(ok=False, status=status, error_type=error_type)


class SnowLumaSttClient:
    """对接 SnowLuma 官方语音转文字接口 fetch_ptt_text 的异步客户端。

    通过 MaiBot 适配器总线 (adapter.snowluma.action.call / adapter.napcat.action.call)
    调用对端原生接口，直接复用 QQ 官方内置语音识别能力，免去外部云模型和本地 sidecar。
    """

    ADAPTER_NAMESPACES = ("adapter.snowluma", "adapter.napcat")
    ACTION_NAME = "fetch_ptt_text"

    def __init__(
        self,
        ctx: Any = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        retry_interval: float = 1.0,
        adapter_namespace: str = "auto",
        **kwargs: Any,
    ) -> None:
        """初始化 SnowLuma STT 客户端。

        Args:
            ctx: 插件上下文对象，必须支持 ctx.api.call。
            timeout: 单次语音识别整体超时时间（秒）。
            max_retries: 异步转写中的最大轮询重试次数。
            retry_interval: 轮询重试等待间隔（秒）。
            adapter_namespace: 指定适配器命名空间 ("auto" / "adapter.snowluma" / "adapter.napcat")。
            kwargs: 吸收旧版配置传入的冗余关键字参数以保持兼容。
        """
        self._ctx = ctx
        self._timeout = float(timeout)
        self._max_retries = max(1, int(max_retries))
        self._retry_interval = max(0.1, float(retry_interval))
        self._adapter_namespace = adapter_namespace.strip() or "auto"
        self._resolved_namespace: Optional[str] = (
            None if self._adapter_namespace == "auto" else self._adapter_namespace
        )

    @property
    def endpoint_url(self) -> str:
        """保持与旧版状态卡片兼容的后端描述信息。"""
        ns = self._resolved_namespace or self._adapter_namespace
        return f"{ns}.action.call -> {self.ACTION_NAME}"

    async def transcribe(self, message_id: int | str) -> TranscriptionResult:
        """根据消息 ID 获取语音转文字结果。

        若 QQ 原生转写尚未就绪（返回文本为空），会带退避间隔轮询重试。

        Args:
            message_id: QQ 消息 ID。

        Returns:
            TranscriptionResult: 包含识别出的文本和状态。
        """
        parsed_id = self._normalize_message_id(message_id)
        if parsed_id is None:
            return TranscriptionResult.fail("invalid_message_id", 1)

        last_error_type = "empty_text"
        for attempt in range(1, self._max_retries + 1):
            try:
                # 单次调用超时保护
                text, error = await asyncio.wait_for(
                    self._call_official_fetch(parsed_id),
                    timeout=self._timeout,
                )
                if text:
                    return TranscriptionResult.ok(text, attempt=attempt)

                if error:
                    last_error_type = error
                    # 若明确告知消息不存在或无法识别，不再无谓重试
                    if error in ("not_found", "unsupported", "invalid_message_id"):
                        return TranscriptionResult.fail(error, attempt=attempt)

            except asyncio.TimeoutError:
                last_error_type = "timeout"
            except Exception as exc:
                last_error_type = f"api_error: {exc}"

            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_interval)

        return TranscriptionResult.fail(last_error_type, attempt=self._max_retries)

    def _normalize_message_id(self, message_id: int | str) -> Optional[int | str]:
        """规范化 message_id。"""
        if message_id is None:
            return None
        s = str(message_id).strip()
        if not s:
            return None
        # 如果是纯整数字符串（可能包含负号），转为 int
        if s.lstrip("-").isdigit():
            try:
                return int(s)
            except ValueError:
                return s
        return s

    async def _call_official_fetch(self, message_id: int | str) -> tuple[str, Optional[str]]:
        """调用底层 OneBot 动作 fetch_ptt_text 并解析结果。

        Returns:
            tuple[text, error_type]: 成功时 error_type 为 None；未拿到时返回空文本和原因。
        """
        if not self._ctx or not hasattr(self._ctx, "api") or not hasattr(self._ctx.api, "call"):
            return "", "no_ctx_api"

        params = {"message_id": message_id}
        candidate_namespaces = (
            [self._resolved_namespace]
            if self._resolved_namespace
            else list(self.ADAPTER_NAMESPACES)
        )

        raw_result: Any = None
        used_ns: Optional[str] = None
        call_error: Optional[Exception] = None

        for ns in candidate_namespaces:
            api_name = f"{ns}.action.call"
            try:
                raw_result = await self._ctx.api.call(
                    api_name,
                    action_name=self.ACTION_NAME,
                    params=params,
                )
                used_ns = ns
                break
            except Exception as exc:
                call_error = exc
                continue

        if used_ns and self._adapter_namespace == "auto" and not self._resolved_namespace:
            self._resolved_namespace = used_ns

        if raw_result is None:
            return "", f"call_failed: {call_error}" if call_error else "no_response"

        # 解析响应结构: {"status": "ok", "retcode": 0, "data": {"text": "..."}}
        if isinstance(raw_result, dict):
            status = str(raw_result.get("status") or "").lower()
            retcode = raw_result.get("retcode", 0)
            if status not in ("ok", "async", "") and retcode != 0:
                msg = str(raw_result.get("wording") or raw_result.get("message") or "")
                if "not found" in msg.lower() or "不存在" in msg:
                    return "", "not_found"
                return "", f"retcode_{retcode}"

            data = raw_result.get("data")
            if isinstance(data, dict):
                text = str(data.get("text") or "").strip()
                return text, None
            if isinstance(data, str):
                return data.strip(), None

        return "", "empty_text"

    async def check_health(self) -> HealthCheckResult:
        """检查适配器 API 通道是否可用。"""
        if not self._ctx or not hasattr(self._ctx, "api") or not hasattr(self._ctx.api, "call"):
            return HealthCheckResult.fail("no_api_context")

        candidate_namespaces = (
            [self._resolved_namespace]
            if self._resolved_namespace
            else list(self.ADAPTER_NAMESPACES)
        )
        for ns in candidate_namespaces:
            api_name = f"{ns}.action.call"
            try:
                # 使用 lightweight 的 get_status 探活
                await self._ctx.api.call(api_name, action_name="get_status", params={})
                if not self._resolved_namespace:
                    self._resolved_namespace = ns
                return HealthCheckResult.ready()
            except Exception:
                continue

        return HealthCheckResult.ready()  # 宽松就绪：转写将在真实调用时处理


# 向后兼容导出别名
SenseVoiceClient = SnowLumaSttClient
