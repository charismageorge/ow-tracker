# 🏆 Overwatch Team Tracker V2.8

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-teal.svg)](https://fastapi.tiangolo.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-CSS-38bdf8.svg)](https://tailwindcss.com/)

一个专为 **守望先锋 (Overwatch) 车队** 定制的自动化战力追踪、去水周报看板与微信推送系统。支持跨平台本地开发、无外网真实的 Mock 单元测试方案、以及静态网页一键归档与 GitHub Pages 托管。

---

## 🌟 核心特性

- **🚀 智能化数据抓取与去水**：通过对接开源 `Overfast API` 自动获取全队玩家 summary 与 stats，并通过智能去水算法（Delta 引擎）排除未游玩时段，精准统计过去 7 天内车队成员的真实战斗增量。
- **🏆 趣味“大王”颁奖台**：内置11项车队专属趣味大奖（如*“狗运小子”*、*“确实是会保活大王”*、*“传奇刮痧大王”*、*“本周小天使”*等），自动根据战局表现颁发并带有详细评选标准弹窗。
- **🛡️ 职责一拆三 (Role Breakdown)**：在深度分析面板中可一键切换 **重装 (Tank) / 输出 (Damage) / 支援 (Support)** 位置，查看各职责专属雷达图、KDA 及英雄火力拆解。
- **🎬 复盘录像与趋势分析**：支持绑定每个队员的精彩 VOD 录像链接（如 Bilibili 复盘），支持历史趋势追踪。
- **📱 微信机器人推送**：支持通过 `WxPusher` 在每周日定时向车队微信推送战报摘要。
- **📦 零成本静态化发布**：支持将周报自动打包导出为纯静态 JSON 并推送到 GitHub Pages，随时随地免服务器开箱即用。

---

## 🛠️ 项目结构

```text
ow-tracker/
├── main.py               # FastAPI 后端服务、Delta 抓取与分析引擎
├── export.py             # 静态周报打包脚本 (生成 docs/data/latest.json)
├── generate_mock_data.py # 测试数据库 Mock 生成脚本
├── test_main.py          # 单元测试与端到端 API 测试套件
├── requirements.txt      # Python 依赖清单
├── docker-compose.yml    # Docker 容器编排 (含可选 Cloudflare Tunnel)
├── config.example.json   # 配置文件模板
└── docs/                 # GitHub Pages 静态前端看板
    ├── index.html        # 前端单页面应用 (Tailwind CSS + Chart.js)
    └── data/             # 归档的静态 JSON 数据
```

---

## 🧪 本地化开发与测试方案 (Local Testing & Development)

为了方便任何人开源修改、在不同平台（Windows / macOS / Linux）上开发并进行本地测试，本项目设计了一套 **“零真实依赖”的隔离测试与 Mock 方案**。

### 1. 环境准备

确保您的本地机器已安装 **Python 3.11+**。克隆仓库后，安装依赖：

```bash
pip install -r requirements.txt
```

### 2. 本地配置文件初始化

将配置模板复制一份为 `config.json`（实际生产和真实抓取时使用）：

```bash
cp config.example.json config.json
```
*(注：如果只是本地预览或跑测试，系统会自动使用隔离的测试配置和 Mock 数据库，无需真实 BattleTag 也能完整跑通测试！)*

### 3. 一键执行本地化单元测试

本项目提供完整的 `unittest` 单元测试套件 (`test_main.py`)，它会自动在隔离的内存/临时文件环境中生成车队模拟数据，并对 API 契约、大王颁奖算法、趋势分析进行全方位自动化断言：

```bash
python -m unittest test_main.py
```

**测试输出示例**：
```text
..
----------------------------------------------------------------------
Ran 3 tests in 0.315s

OK
```

### 4. 本地启动 FastAPI 开发服务器

如果您想在本地网页上实时预览看板：

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
- 访问本地前端看板：[http://127.0.0.1:8000](http://127.0.0.1:8000)
- 访问后端 API 文档 (Swagger)：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🐳 使用 Docker 快速部署

如果您习惯使用 Docker，可以直接通过 `docker-compose` 启动：

```bash
docker-compose up -d
```
服务将在本地 `8000` 端口启动，并自带热重载。

---

## 🚀 如何开源与配置线上服务

1. **修改 `config.json`**：
   填入你们车队的真实战网昵称 (`TEAM_MEMBERS`)、`WxPusher` 微信推送 Token 与 UID、以及你的 GitHub 个人访问令牌 (`GITHUB_TOKEN`) 和仓库名 (`GITHUB_REPO`) 用于自动同步 GitHub Pages。
2. **配置 GitHub Pages**：
   在你的 GitHub 仓库设置中，将 Pages 的发布源 (Source) 指向 `main` 分支的 `/docs` 文件夹。
3. **享受车队战力周报**：
   系统会在每周定时抓取、颁发大王、推送到微信，并将最新周报静态化挂载至网页！

---