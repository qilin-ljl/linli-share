# NeighLoop

一个面向小区、楼栋和办公室的闲置流转演示应用。支持社区定位与手动选择、照片辅助发布、批量清闲置、明确需求匹配、预约交接和物品流转护照。

下载本地运行压缩包并解压后，可双击 `Open-NeighLoop.bat` 安装、启动并打开浏览器；详细说明见 [LOCAL_RUN.md](LOCAL_RUN.md)。本地源码目录也可按下方步骤分别启动前后端。

## 本地运行（Windows PowerShell）

需要 Node.js 20+、Python 3.12+。项目使用 PostgreSQL URL 时连接 PostgreSQL；未设置 `DATABASE_URL` 时使用本地 SQLite 方便直接体验。线上请使用持久化 PostgreSQL。

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 在 backend/.env 中设置自己的 DEEPSEEK_API_KEY 和固定的随机 JWT_SECRET_KEY
# 本地演示用户／测试账号：将 NEIGHLOOP_DEMO_MODE 设为 true
# 如果电脑上已有旧版 neighloop.db，先运行：.\.venv\Scripts\python.exe migrate.py
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

另开一个终端：

```powershell
cd frontend
npm install
# 如需演示身份切换：在 frontend/.env.local 写入 VITE_DEMO_MODE=true
npm run dev -- --host 127.0.0.1
```

打开 `http://127.0.0.1:5173/`。API 文档位于 `http://127.0.0.1:8000/docs`。种子命令可重复运行，保留现有内容，并补齐 3 个演示社区、58 件额外闲置、16 条额外需求、预约／成交记录与一件两次流转的台灯护照。`migrate.py` 处理更早版本的预约／事件字段；后续字段由 `create_db()` 在启动或运行 `seed.py` 时自动迁移。也可单独运行：

真机录屏需要让手机通过同一 Wi-Fi 访问电脑的局域网 IP，不能在手机输入 `127.0.0.1`。启动命令、CORS 设置、双人操作顺序及逐秒旁白见 [手机端 5 分钟录制执行稿](docs/DEMO_SCRIPT.md)。

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from database import create_db; create_db()"
```

迁移会保留现有演示用户和物品；`backend/migrate_features.py` 增加坐标、需求、批量发布、护照及私聊字段／表，并为已有成交物品回填护照。首次升级前建议备份 `backend/neighloop.db`。

## 演示流程

1. 游客可浏览首页、市集、地图、详情和社区数据；点击发布、预约、留言或个人中心时出现登录提示。
2. 注册邮箱账号后完成四步配置：社区、目标、类别、交易偏好。随后进入新的双频道首页，依次引导频道、搜索筛选、分开发布和私聊预约。
3. 每次重新打开或刷新项目，先展示约 2.6 秒品牌动效，再进入“闲置市集／邻里需求”双频道首页；站内切换页面不会重复播放。市集推荐可横向滑动，依据已完成领取的物品类别和主动偏好排序；需求频道提供关键词、类别、楼栋、回应状态和预算筛选，不包含发布表单。
4. 若启用本地 Demo 模式，可在顶部切换“林小雨”等演示邻居，快速演示双方流程。
5. 底部发布入口分别进入闲置发布页与独立的需求发布页；发布后返回需求频道。买家在详情页选择时间后进入私聊；卖家在消息页接受预约，买家可查看 4 位领取码并更新出发／到达状态。FAQ 可由标注身份的 AI 助手按物品事实回答。
6. 发布者输入正确号码完成交接。完整物品时间线只对发布者开放；社区动态只显示不含个人身份的公开事件。
7. 顶部社区按钮可手动搜索、查看最近访问，或在主动授权定位后匹配附近社区。云栖花园的本地演示坐标是 `31.2304, 121.4737`。
8. 发布页可切换普通发布、AI 拍照发布和搬家清闲置。照片分析只提取可见事实，价格由独立定价服务计算；用户逐件核对后才写入数据库。
9. 云栖花园地图可切换“闲置物品／邻里需求”，下方显示社区数据；3号楼有 4 条厨房小家电需求。发布匹配物品后，详情页显示基于类别、关键词和预算的理由。
   “我在找”支持自由描述：DeepSeek 可给出最多 3 条明确标注为推测的候选物品。用户选择或修改后才发布；未在原话中给出的预算不会由 AI 代填。后续匹配只使用用户最终确认的类别、关键词与预算。需求池也可展开邻里讨论，并附上回复者自己的在架物品。
10. 打开云栖花园已完成的“护照演示：北欧风台灯”，可见两次发布和两次成交。当前拥有者可从详情页再次发布。

本地测试账号仅在 `NEIGHLOOP_DEMO_MODE=true` 且运行 `seed.py` 时创建：`test@example.com`（未完成首次配置）和 `returning@example.com`（已完成配置）。两者测试密码默认均为 `NeighLoopDemo2026!`，可通过 `NEIGHLOOP_SEED_PASSWORD` 覆盖。生产环境关闭 Demo 模式，不使用这些账号或密码。

## 主要功能与结构

| 目录 | 职责 |
| --- | --- |
| `frontend/` | React + TypeScript + Vite，市集、地图、发布、详情、数据与个人页 |
| `backend/main.py` | FastAPI 路由、业务规则、统计、DeepSeek 调用 |
| `backend/models.py` | SQLModel 数据实体与约束 |
| `backend/auth.py` | Argon2 密码哈希、JWT 签发与校验、Demo 身份隔离 |
| `backend/migrations.py` | 现有 User 表的账号字段迁移 |
| `backend/migrate_features.py` | 社区坐标、需求、批量发布和护照的增量迁移与历史回填 |
| `backend/migrate.py` | 旧数据库的幂等字段／预约表升级与交接时间回填 |
| `backend/services/ai_pricing_service.py` | 三档价格策略及明确标注的规则兜底 |
| `backend/services/visual_analysis_service.py` | 多图可见事实分析；不可用时明确要求人工核对 |
| `backend/services/need_parser_service.py` | 明确需求解析与标记为规则参考的兜底 |
| `backend/services/need_matching_service.py` | 只按类别、关键词和预算匹配明确需求 |
| `backend/services/item_events.py` | 统一物品事件写入与时间线／公开动态文案 |
| `backend/seed.py` | 基础物品、演示账号、社区及护照数据 |
| `backend/seed_more.py` | 可重复补种的 58 件跨社区物品、16 条需求及关联互动／交易记录 |
| `frontend/src/ItemTimeline.tsx` | 商品生命周期时间线 |
| `frontend/src/CommunityActivityFeed.tsx` | 手机市集右上角固定轮播、每 8 秒刷新公开动态 |
| `frontend/src/pages/MessagesPage.tsx` | 私聊列表、我想要、预约和交接操作 |
| `frontend/src/pages/AuthPage.tsx` | 邮箱注册与登录 |
| `frontend/src/pages/OnboardingPage.tsx` | 新用户四步配置与欢迎过渡 |
| `frontend/src/ProductTour.tsx` | 新首页四步真实组件聚焦引导 |
| `frontend/src/CommunitySelector.tsx` | 主动定位、最近访问和手动社区搜索 |
| `frontend/src/VisualPublishPanel.tsx` | 同一物品 2–5 张照片的分析与定价确认 |
| `frontend/src/BatchPublishPanel.tsx` | 多图拆分、逐件编辑与批量确认发布 |
| `frontend/src/pages/NeedsPage.tsx` | 邻里需求浏览频道、筛选、讨论与在架物品回复 |
| `frontend/src/pages/PublishNeedPage.tsx` | 独立的 AI 需求发布与个人需求管理 |
| `frontend/src/pages/PassportPage.tsx` | 从事件和成交记录生成的流转护照 |
| `frontend/src/HandoverProgress.tsx` | 买家出发／到达／晚到与卖家超时处理 |
| `frontend/public/images/` | 社区底图和三张物品示例照片图集 |
| `docs/` | ER 图与技术栈简介 |

前端只通过后端 API 读写业务数据。正式账号使用 Argon2 密码哈希与 7 天有效的 JWT；JWT 存在 HttpOnly Cookie，退出时撤销服务端会话。Demo 身份请求头仅在后端 `NEIGHLOOP_DEMO_MODE=true` 时有效。`DEEPSEEK_API_KEY` 只由后端读取。社区写入按成员关系隔离，公开浏览按当前社区筛选。

视觉分析默认复用 `DEEPSEEK_API_KEY`、`deepseek-flash` 和 DeepSeek 官方地址；需要其他 OpenAI 兼容视觉服务时设置 `VISION_API_KEY`、`VISION_BASE_URL`、`VISION_MODEL`。图片只在用户点击分析后由后端发送给视觉服务。DeepSeek 的[视觉接口文档](https://api-docs.deepseek.com/guides/vision/)说明其支持图片输入；定价服务仍与视觉识别分开运行。

## 运行检查

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_tmp

cd ..\frontend
npm run build
npm run lint
```

后端测试覆盖账号、上传、显式偏好、社区隔离、需求匹配、批量发布、护照再次流转、地址分级与预约交接。上线前仍需在真实域名下复查 Cookie、CORS、持久化图片存储和完整移动端流程。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy 数据库 URL；线上应为托管 PostgreSQL |
| `DEEPSEEK_API_KEY` | DeepSeek 密钥，仅在后端配置 |
| `DEEPSEEK_MODEL` | 默认 `deepseek-flash` |
| `VISION_API_KEY` | 可选视觉服务 Key；留空时复用 `DEEPSEEK_API_KEY` |
| `VISION_BASE_URL` | 可选 OpenAI 兼容视觉服务地址；默认 DeepSeek 官方接口 |
| `VISION_MODEL` | 可选视觉模型；默认 `deepseek-flash` |
| `CORS_ORIGINS` | 允许访问 API 的前端来源，逗号分隔 |
| `VITE_API_URL` | 前端构建时的后端 API 根地址 |
| `JWT_SECRET_KEY` | JWT 签名密钥；生产环境必须配置固定、随机的密钥 |
| `NEIGHLOOP_DEMO_MODE` | 后端演示身份开关；生产设为 `false` |
| `VITE_DEMO_MODE` | 前端演示切换器开关；生产设为 `false` |
| `NEIGHLOOP_SEED_PASSWORD` | 仅本地种子账号的测试密码 |

本地 `.env` 已被 `.gitignore` 忽略。不要把密钥放在 `VITE_` 开头的变量中。

## 已知边界

- 地图是现有 2.5D 社区示意图，不是真实 GIS。云栖花园的坐标和需求属于明确标注的演示数据；真实社区需由创建者自愿标记位置。只有用户主动授权定位才显示近似距离，精确坐标不返回给普通物品列表。
- 实拍照片目前存储在本机 `backend/uploads/`，部署前需改成持久化对象存储。
- 当前是邮箱密码登录，没有邮箱验证、密码找回、短信和第三方登录。写操作使用 SameSite Cookie 与自定义请求头；公开上线前仍需完成限流、滥用防护和安全复核。
- 图片视觉识别与批量拆分需要可用的视觉 API；失败时只能生成需要人工核对的草稿，不会冒充识别结论。批量拆分目前按每张照片最主要的待发布物品处理；复杂同框多物品需要用户逐件调整。
- 照片支持 JPG／PNG／WebP，单张不超过 12 MB；后端转正方向、去除 EXIF 等原始元数据并保存 JPEG，视觉模型接收进一步缩小的副本。私有社区照片只向社区成员提供。
- 私聊和社区动态采用轮询，没有 WebSocket；不包含支付、物流或后台定时超时释放。
