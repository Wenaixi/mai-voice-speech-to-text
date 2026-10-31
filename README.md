# SenseVoice STT 语音转文字

[![Release](https://img.shields.io/github/v/release/Wenaixi/mai-voice-speech-to-text?style=flat-square&color=blue&label=release)](https://github.com/Wenaixi/mai-voice-speech-to-text/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/Wenaixi/mai-voice-speech-to-text/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/Wenaixi/mai-voice-speech-to-text/actions)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue?style=flat-square)](https://www.python.org/)
[![MaiBot](https://img.shields.io/badge/MaiBot-1.2%2B-orange?style=flat-square)](https://docs.mai-mai.org)

> 本插件由 [Wenaixi](https://github.com/Wenaixi) 维护，是专为生产环境深度调优的高可用分支。

## 简介与定位

将入站 QQ 语音消息通过本地/远程 SenseVoice 模型实时识别为文字供大模型阅读。

- **插件目录**：`wenaixi_mai_voice_speech_to_text`
- **开源许可证**：`MIT`

---

## 核心特性与本地深度调优

- 入站消息前置拦截过滤，兼容 Silk 音频编码转换

---

## 指令与工具速查

### 常用指令 (Command)
- `(后台拦截处理型插件，无独立命令)`

### 大模型工具 (Tool)
- `(消息前置 Hook 自动转写，无独立工具)`

---

## 快速配置

配置文件统一定位于插件根目录下的 `config.toml`。修改后重启或通过 WebUI 热重载即可生效。

---

## 上游项目与开源溯源

- **原作者 / 组织**：`dmjxmj`
- **官方原版开源仓库**：[https://github.com/dmjxmj/maibot-sensevoice-stt](https://github.com/dmjxmj/maibot-sensevoice-stt)
- **开源协议**：`MIT`
- **声明**：本项目遵循开源协议，特此致敬原作者的杰出贡献。本分支针对生产环境的高并发网络、个性化社交和抗风控需求进行了深度稳定性修复与定制化演进。