# NeighLoop 本地压缩包运行说明（Windows）

这份压缩包包含源码、静态图片、数据库初始化脚本、测试和演示文档。**不包含**作者电脑的数据库、上传文件、Python 虚拟环境、`node_modules` 或任何 `.env` 密钥；首次安装依赖需要联网。

## 环境

- Windows 10/11，PowerShell。
- Python 3.12，并能运行 `py -3.12 --version`。
- Node.js 20.19+ 或 22.12+，并能运行 `node --version` 与 `npm --version`。

## 双击运行

将压缩包完整解压后，双击 `Open-NeighLoop.bat`。首次运行会安装依赖、初始化演示数据，然后自动启动前后端并打开浏览器；后续双击会直接打开本地项目，并给演示物品补齐未来可领取时间，不改用户自己发布的物品或已有预约。首次安装需要联网，以及下方列出的 Python 和 Node.js 版本。若启动失败，窗口会保留错误信息供排查。

停止服务仍使用 `stop_local.ps1`；再次打开时可重新双击批处理文件。

## 手动运行

将压缩包完整解压，PowerShell 进入解压得到的 `NeighLoop` 文件夹：

```powershell
.\setup_local.ps1
.\start_local.ps1
```

浏览器打开 **http://127.0.0.1:5173/**。API 文档是 **http://127.0.0.1:8000/docs**。首次设置会安装 Python／Node 依赖、生成独立的本地 SQLite 演示库、生成本机专用的 JWT 密钥，并开启 Demo 身份切换。以后启动只需 `start_local.ps1`。停止服务：

```powershell
.\stop_local.ps1
```

启动后端和前端的日志在 `.local-run/`。若 8000 或 5173 端口已被别的进程使用，可以先停掉旧服务，或用 `.\start_local.ps1 -ApiPort 8001 -WebPort 5174` 选择其他本机端口；前端会自动连接所选 API 端口。

## DeepSeek 功能

设置脚本只创建 `backend/.env`，其中 `DEEPSEEK_API_KEY` 留空。想使用描述润色、定价、需求解析和 FAQ 时，把**自己的** Key 填到解压目录的 `backend/.env` 中，然后停止并重新启动。不要把 Key 放到前端变量、提交文件或录屏画面里。未填 Key 时，市集、地图、发布、预约和私聊的非 AI 路径仍可在本地运行；需要 AI 的按钮会提示未配置或使用明确标注的规则兜底。

## 数据与演示

`setup_local.ps1` 运行 `backend/seed.py`，生成多个演示社区、示例物品、需求、讨论回复及成交记录。种子脚本可重复运行，不会覆盖用户自己发布的物品。预约时段会随时间过期；录制完整交接时，建议现场发布一件新物品并使用未来时段。五分钟录屏路线见 [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)。

本地数据库在 `backend/neighloop.db`，用户上传照片在 `backend/uploads/`；两者都不会被再次生成的压缩包带走。需要保留自己的数据时，自行备份这两个位置，勿公开其中的账号或私人消息。

## 用真实手机访问

默认 `start_local.ps1` 只供当前电脑访问。如果想让同一 Wi-Fi 的手机访问，请按 [手机录屏执行稿的局域网启动步骤](docs/DEMO_SCRIPT.md#二录制前检查真机访问本地项目) 单独启动两个服务并设置当前电脑的局域网 IP 与 `CORS_ORIGINS`。这属于局域网本地演示，不等于公开部署。
