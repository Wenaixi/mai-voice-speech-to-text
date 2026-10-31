"""测试 plugin — mock maibot_sdk 和客户端，验证 Hook/Command/HomeCard。"""

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

# ---- mock maibot_sdk ----

_mock_types = MagicMock()
_mock_types.ErrorPolicy = MagicMock()
_mock_types.ErrorPolicy.SKIP = "SKIP"
_mock_types.HookMode = MagicMock()
_mock_types.HookMode.BLOCKING = "BLOCKING"
_mock_types.HookOrder = MagicMock()
_mock_types.HookOrder.EARLY = "EARLY"

class _MockPluginBase:
    def __init__(self):
        self.ctx = MagicMock()
        self.ctx.logger = MagicMock()
        self.ctx.api = MagicMock()
        self.ctx.api.call = AsyncMock()
        self.config = MagicMock()


def _install_plugin_mocks():
    mock_sdk = types.ModuleType("maibot_sdk")
    mock_sdk.HomeCard = lambda *a, **kw: lambda fn: fn
    mock_sdk.HookHandler = lambda *a, **kw: lambda fn: fn
    mock_sdk.Command = lambda **kw: lambda fn: fn
    mock_sdk.MaiBotPlugin = _MockPluginBase
    mock_sdk.PluginConfigBase = type("PluginConfigBase", (), {})
    mock_sdk.Field = lambda *a, **kw: {"args": a, "kwargs": kw}

    sys.modules["maibot_sdk"] = mock_sdk
    sys.modules["maibot_sdk.types"] = _mock_types


_install_plugin_mocks()

# ---- 被测模块加载 ----

import importlib
import importlib.util

_plugin_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))

_pkg = types.ModuleType("_stt_pkg")
_pkg.__path__ = [_plugin_dir]
_pkg.__file__ = os.path.join(_plugin_dir, "__init__.py")
sys.modules["_stt_pkg"] = _pkg

_spec = importlib.util.spec_from_file_location(
    "_stt_pkg.plugin",
    os.path.join(_plugin_dir, "plugin.py"),
    submodule_search_locations=[_plugin_dir],
)
pmod = importlib.util.module_from_spec(_spec)
pmod.__package__ = "_stt_pkg"
sys.modules["_stt_pkg.plugin"] = pmod
_spec.loader.exec_module(pmod)


def _reload_plugin_module():
    _install_plugin_mocks()
    importlib.reload(pmod)


class TestRebuildPlainText(unittest.TestCase):
    def setUp(self):
        _reload_plugin_module()

    def test_all_types(self):
        segs = [
            {"type": "text", "data": "你好"},
            {"type": "voice"},
            {"type": "image"},
            {"type": "reply"},
        ]
        result = pmod.rebuild_plain_text(segs)
        self.assertEqual(result, "你好[voice][image][reply]")

    def test_transcribed_voice(self):
        segs = [
            {"type": "text", "data": "听到消息："},
            {"type": "voice", "data": "[voice]这是语音内容"},
        ]
        result = pmod.rebuild_plain_text(segs)
        self.assertEqual(result, "听到消息：[voice]这是语音内容")

    def test_mixed_text_voice(self):
        segs = [
            {"type": "text", "data": "前面"},
            {"type": "voice"},
            {"type": "text", "data": "后面"},
        ]
        result = pmod.rebuild_plain_text(segs)
        self.assertEqual(result, "前面[voice]后面")

    def test_only_text(self):
        segs = [{"type": "text", "data": "纯文本"}]
        result = pmod.rebuild_plain_text(segs)
        self.assertEqual(result, "纯文本")

    def test_empty_segments(self):
        result = pmod.rebuild_plain_text([])
        self.assertEqual(result, "[unsupported]")

    def test_non_dict_items_skipped(self):
        segs = [{"type": "text", "data": "a"}, "not_a_dict"]
        result = pmod.rebuild_plain_text(segs)
        self.assertEqual(result, "a")


class TestCreatePlugin(unittest.TestCase):
    def setUp(self):
        _reload_plugin_module()

    def test_returns_plugin_instance(self):
        p = pmod.create_plugin()
        self.assertIsInstance(p, pmod.VoiceSttPlugin)


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        _reload_plugin_module()
        self.p = pmod.VoiceSttPlugin()
        self.p.config.plugin.enabled = True
        self.p.config.stt.timeout_seconds = 15
        self.p.config.stt.max_retries = 3
        self.p.config.stt.retry_interval = 0.01
        self.p.config.stt.adapter_namespace = "auto"

    def test_on_load_inits_client(self):
        asyncio.run(self.p.on_load())
        self.assertIsNotNone(self.p._client)

    def test_on_load_disabled(self):
        self.p.config.plugin.enabled = False
        asyncio.run(self.p.on_load())
        self.assertIsNone(self.p._client)

    def test_on_unload_clears_client(self):
        asyncio.run(self.p.on_load())
        asyncio.run(self.p.on_unload())
        self.assertIsNone(self.p._client)

    def test_on_config_update_self_scope(self):
        self.p._client = None
        asyncio.run(self.p.on_config_update("self", {}, "0.2.0"))
        self.assertIsNotNone(self.p._client)

    def test_on_config_update_ignored_scope(self):
        self.p._client = None
        asyncio.run(self.p.on_config_update("bot", {}, "0.2.0"))
        self.assertIsNone(self.p._client)


class TestTranscribeHook(unittest.TestCase):
    def setUp(self):
        _reload_plugin_module()
        self.p = pmod.VoiceSttPlugin()
        self.p.config.plugin.enabled = True
        self.p.config.stt.timeout_seconds = 15
        self.p.config.stt.max_retries = 3
        self.p.config.stt.retry_interval = 0.01
        self.p.config.stt.adapter_namespace = "auto"
        asyncio.run(self.p.on_load())

    def test_no_voice_segments(self):
        """入站无语音段时不触发 API 调用。"""
        msg = {
            "message_id": 1001,
            "raw_message": [{"type": "text", "data": "普通文字"}],
            "processed_plain_text": "普通文字",
        }
        result = asyncio.run(self.p.transcribe_voice_segments(message=msg))
        self.assertIsNone(result)
        self.assertEqual(self.p._stats["total_requests"], 0)

    def test_no_message_returns_none(self):
        result = asyncio.run(self.p.transcribe_voice_segments(message=None))
        self.assertIsNone(result)

    def test_no_client_returns_none(self):
        self.p._client = None
        msg = {"message_id": 1002, "raw_message": [{"type": "voice"}]}
        result = asyncio.run(self.p.transcribe_voice_segments(message=msg))
        self.assertIsNone(result)

    def test_missing_message_id_skips(self):
        """入站有语音段但缺少 message_id 时安全跳过。"""
        msg = {
            "raw_message": [{"type": "voice"}],
            "processed_plain_text": "[voice]",
        }
        result = asyncio.run(self.p.transcribe_voice_segments(message=msg))
        self.assertIsNone(result)
        self.assertEqual(self.p._stats["total_requests"], 0)

    def test_transcribe_voice_success(self):
        """语音转文字成功时，原地替换语音段并重建文本。"""
        self.p.ctx.api.call.return_value = {
            "status": "ok",
            "retcode": 0,
            "data": {"text": "明天下午一起喝咖啡吧"},
        }
        msg = {
            "message_id": 88888,
            "raw_message": [
                {"type": "text", "data": "主人说："},
                {"type": "voice", "data": ""},
            ],
            "processed_plain_text": "主人说：[voice]",
            "display_message": "主人说：[voice]",
        }
        result = asyncio.run(self.p.transcribe_voice_segments(message=msg))

        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "continue")
        updated_msg = result["modified_kwargs"]["message"]
        self.assertEqual(updated_msg["raw_message"][1]["type"], "text")
        self.assertEqual(updated_msg["raw_message"][1]["data"], "[语音: 明天下午一起喝咖啡吧]")
        self.assertEqual(updated_msg["processed_plain_text"], "主人说：[语音: 明天下午一起喝咖啡吧]")
        self.assertEqual(updated_msg["display_message"], "主人说：[语音: 明天下午一起喝咖啡吧]")
        self.assertEqual(self.p._stats["total_success"], 1)

    def test_transcribe_voice_failure(self):
        """转写失败时不阻断原消息，安全替换为 [语音: 无法识别到文字]。"""
        self.p.ctx.api.call.return_value = {
            "status": "failed",
            "retcode": 100,
            "message": "voice transcode error",
        }
        msg = {
            "message_id": 99999,
            "raw_message": [{"type": "voice", "data": ""}],
            "processed_plain_text": "[voice]",
        }
        result = asyncio.run(self.p.transcribe_voice_segments(message=msg))
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "continue")
        updated_msg = result["modified_kwargs"]["message"]
        self.assertEqual(updated_msg["raw_message"][0]["data"], "[语音: 无法识别到文字]")
        self.assertEqual(updated_msg["processed_plain_text"], "[语音: 无法识别到文字]")
        self.assertEqual(self.p._stats["total_failure"], 1)

    def test_transcribe_voice_empty_content(self):
        """转写成功但无文本时，替换为 [语音: 无法识别到内容]。"""
        self.p.ctx.api.call.return_value = {
            "status": "ok",
            "data": {"text": ""},
        }
        msg = {
            "message_id": 99998,
            "raw_message": [{"type": "voice", "data": ""}],
            "processed_plain_text": "[voice]",
        }
        result = asyncio.run(self.p.transcribe_voice_segments(message=msg))
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "continue")
        updated_msg = result["modified_kwargs"]["message"]
        self.assertEqual(updated_msg["raw_message"][0]["data"], "[语音: 无法识别到内容]")
        self.assertEqual(updated_msg["processed_plain_text"], "[语音: 无法识别到内容]")
        self.assertEqual(self.p._stats["total_failure"], 1)

    def test_home_card(self):
        """测试状态卡片输出正确。"""
        card = asyncio.run(self.p.stt_home_card())
        self.assertIn("blocks", card)
        entries = card["blocks"][0]["entries"]
        self.assertEqual(entries["插件状态"], "启用")
        self.assertEqual(entries["驱动方式"], "SnowLuma 官方 fetch_ptt_text")


if __name__ == "__main__":
    unittest.main()