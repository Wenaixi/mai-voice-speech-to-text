"""测试 SnowLumaSttClient — 验证底层 fetch_ptt_text 调用与异步重试机制。"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.stt_client import HealthCheckResult, SnowLumaSttClient, TranscriptionResult


class TestSnowLumaSttClient(unittest.TestCase):
    def setUp(self):
        self.mock_ctx = MagicMock()
        self.mock_ctx.api = MagicMock()
        self.mock_ctx.api.call = AsyncMock()

    def test_transcribe_success_immediate(self):
        """测试单次调用立即成功拿到识别文本。"""
        self.mock_ctx.api.call.return_value = {
            "status": "ok",
            "retcode": 0,
            "data": {"text": "你好，这是一条语音测试"},
        }
        client = SnowLumaSttClient(ctx=self.mock_ctx, timeout=5.0, max_retries=3, retry_interval=0.01)
        result = asyncio.run(client.transcribe(123456))

        self.assertTrue(result.success)
        self.assertEqual(result.text, "你好，这是一条语音测试")
        self.assertEqual(result.attempt, 1)
        self.mock_ctx.api.call.assert_awaited_once_with(
            "adapter.snowluma.action.call",
            action_name="fetch_ptt_text",
            params={"message_id": 123456},
        )

    def test_transcribe_retry_success(self):
        """测试首次服务端异步转写为空，第二轮轮询成功获取文本。"""
        self.mock_ctx.api.call.side_effect = [
            {"status": "ok", "retcode": 0, "data": {"text": ""}},
            {"status": "ok", "retcode": 0, "data": {"text": "轮询成功结果"}},
        ]
        client = SnowLumaSttClient(ctx=self.mock_ctx, timeout=5.0, max_retries=3, retry_interval=0.01)
        result = asyncio.run(client.transcribe("987654"))

        self.assertTrue(result.success)
        self.assertEqual(result.text, "轮询成功结果")
        self.assertEqual(result.attempt, 2)
        self.assertEqual(self.mock_ctx.api.call.await_count, 2)

    def test_transcribe_namespace_fallback(self):
        """测试 adapter.snowluma 抛异常时自动 fallback 到 adapter.napcat。"""
        self.mock_ctx.api.call.side_effect = [
            RuntimeError("API not found: adapter.snowluma.action.call"),
            {"status": "ok", "retcode": 0, "data": {"text": "NapCat 成功返回"}},
        ]
        client = SnowLumaSttClient(ctx=self.mock_ctx, timeout=5.0, max_retries=2, retry_interval=0.01)
        result = asyncio.run(client.transcribe(111222))

        self.assertTrue(result.success)
        self.assertEqual(result.text, "NapCat 成功返回")
        # 验证第一次调 snowluma，第二次调 napcat
        calls = self.mock_ctx.api.call.await_args_list
        self.assertEqual(calls[0][0][0], "adapter.snowluma.action.call")
        self.assertEqual(calls[1][0][0], "adapter.napcat.action.call")

    def test_transcribe_not_found_fast_fail(self):
        """测试当对端返回消息不存在时，快速失败且不再盲目重试。"""
        self.mock_ctx.api.call.return_value = {
            "status": "failed",
            "retcode": 100,
            "message": "message not found",
        }
        client = SnowLumaSttClient(ctx=self.mock_ctx, timeout=5.0, max_retries=3, retry_interval=0.01)
        result = asyncio.run(client.transcribe(404))

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "not_found")
        self.assertEqual(result.attempt, 1)

    def test_invalid_message_id(self):
        """测试无效 message_id 直接拦截。"""
        client = SnowLumaSttClient(ctx=self.mock_ctx)
        result = asyncio.run(client.transcribe(""))
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "invalid_message_id")

        result_none = asyncio.run(client.transcribe(None))
        self.assertFalse(result_none.success)
        self.assertEqual(result_none.error_type, "invalid_message_id")

    def test_check_health(self):
        """测试健康检查探活。"""
        self.mock_ctx.api.call.return_value = {"status": "ok", "retcode": 0}
        client = SnowLumaSttClient(ctx=self.mock_ctx)
        health = asyncio.run(client.check_health())
        self.assertTrue(health.ok)
        self.assertEqual(health.status, "ready")


if __name__ == "__main__":
    unittest.main()
