# 🎵 AMTools - 高质量音乐下载与转换工具

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Deployment](https://img.shields.io/badge/Deployed%20on-Hugging%20Face-ffcc00)](https://huggingface.co/spaces/e1290546670/AMTools)

**AMTools** 是一个专为音乐爱好者打造的在线工具，核心功能是 **将 Apple Music 链接直接转换为 MP3/M4A 音频文件**。

它不仅能帮你下载高解析度的音源，还能通过内置的 FFmpeg 自动完成格式转换，并完美保留专辑封面、艺术家、歌词等所有元数据。
---

## 🚀 在线体验

无需安装任何环境，点击下方链接即可直接使用：

👉 **[立即访问 AMTools](https://e1290546670-amtools.hf.space)** *(注：如果页面显示 Sleeping，请等待约 30 秒自动唤醒)*

---

## ✨ 核心功能

- **一键解析**：支持 Apple Music 链接直接解析下载。
- **高音质转换**：内置 FFmpeg，支持从高码率源文件转换为标准 MP3。
- **元数据保留**：下载的音频自动包含专辑封面、艺术家、歌词等信息。
- **云端部署**：基于 Docker 容器化，部署于 Hugging Face Spaces。

---

## 🛠️ 技术栈

- **后端**: [Flask](https://flask.palletsprojects.com/) (Python)
- **核心引擎**: [gamdl](https://github.com/glomatico/gamdl)
- **多媒体处理**: [FFmpeg](https://ffmpeg.org/)
- **部署环境**: [Hugging Face Spaces](https://huggingface.co/spaces) (Docker Mode)

---

## 📦 本地快速开始

如果你想在本地运行本项目，请确保已安装 **Python 3.9+** 和 **FFmpeg**。


