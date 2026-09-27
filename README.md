# 好友餐厅点评：Tablemates 演示网站

本目录包含可直接操作的英文前端、Flask JSON API、Docker Compose、PostgreSQL 初始化 SQL 和英文虚构数据生成脚本。概念模型对应
[`../v1/9120 Gp.drawio (2).pdf`](../v1/9120%20Gp.drawio%20(2).pdf)。不会修改旧的
`campus-booking-system`。

## 启动

需要先安装并启动 Docker Desktop。在本目录执行：

```powershell
python .\scripts\generate_data.py
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 首次启动前编辑 .env，将 POSTGRES_PASSWORD 改为自己的本地数据库密码。
docker compose up -d --wait
```

## 启动网站和 Python API

在本目录执行（Python 3.11 或更新版本）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

在浏览器打开 **`http://127.0.0.1:5000/`** 即可使用图形界面；`http://127.0.0.1:5000/api` 保留 JSON 接口入口。使用首页的 **Enter demo** 可以直接登录 Alice 演示账号，也可手动输入 `alice.morgan@example.test` / `DemoPass2026!`。网站包含店铺搜索和菜单、整体店铺评价、好友申请和动态、收藏、推荐、聚餐计划、投票和个人到访记录。页面是英文，与模拟数据一致；界面文件位于 `app/templates/index.html`、`app/static/style.css` 和 `app/static/app.js`。

好友特色：首页的 **Where friends have been**、探索页的 **Visited by friends** 筛选，以及店铺卡片会显示最近 90 天去过该店的好友人数和姓名。打开店铺能看到这些好友最近一次共享到访日期，还能在 **All reviews / Friends only** 之间切换。只有已接受的好友会被计入；好友设为 `private` 的到访和评价不会出现在这些信息里。此统计实时查询现有数据库，无须重新生成数据。

如果端口 5000 已被之前启动的旧版 `run.py` 占用，先到运行旧服务的终端按 `Ctrl+C`，再运行上面的启动命令，否则浏览器仍可能显示旧的 JSON 首页。也可以临时换端口：

```powershell
$env:APP_PORT = '5100'
.\.venv\Scripts\python.exe run.py
# 此时打开 http://127.0.0.1:5100/
```

`GET /api/health` 可检查数据库连接。应用自动从本目录 `.env` 读取 `POSTGRES_PASSWORD`，连接本机 `127.0.0.1:5433` 的 Docker PostgreSQL；也可以用 `DATABASE_URL` 覆盖连接信息。`APP_PORT` 可更改监听端口；部署或希望重启后维持登录状态时，应设置固定的 `APP_SECRET_KEY`。默认只监听本机。

当前前端与 API 同源，浏览器登录状态由安全属性为 HttpOnly 的会话 Cookie 保存。所有写操作从登录会话识别当前用户，不接受前端传入的操作者 ID。若另建前端开发服务器并使用另一端口，可设置精确的 `FRONTEND_ORIGIN`（例如 `http://127.0.0.1:5173`），并在 `fetch` 中使用 `credentials: 'include'`。

### 主要接口

| 功能 | 路径与方法 |
|---|---|
| 登录、退出、当前用户 | `POST /api/login`、`POST /api/logout`、`GET /api/me` |
| 首页与搜索 | `GET /api/dashboard`、`GET /api/catalog`、`GET /api/restaurants`、`GET /api/restaurants/{id}` |
| 好友去过的店与评价筛选 | `GET /api/restaurants?friends_only=1&sort=friends`、`GET /api/restaurants/{id}/friend-visits`、`GET /api/restaurants/{id}/reviews?friends_only=1` |
| 店铺评价与好友动态 | `GET /api/restaurants/{id}/reviews`、`GET /api/feed`、`GET /api/reviews/{id}/comments` |
| 用户与好友申请 | `GET /api/users?q=...`、`GET /api/friends`、`POST /api/friend-requests`、`POST /api/friend-requests/{id}/accept` 或 `/reject` |
| 收藏与到访 | `GET/POST /api/favorites`、`DELETE /api/favorites/{restaurant_id}`、`GET /api/me/visits`、`POST /api/visits` |
| 评论与回复 | `POST /api/visits/{id}/review`、`POST /api/reviews/{id}/comments` |
| 推荐 | `GET/POST /api/recommendations`、`PATCH /api/recommendations/{id}` |
| 聚餐计划 | `GET/POST /api/plans`、`GET /api/plans/{id}`、`POST /api/plans/{id}/rsvp`、`/open`、`/vote`、`/finalize`、`/cancel` |

所有写入请求使用 JSON。Alice 演示账号：`alice.morgan@example.test`，密码 `DemoPass2026!`。例如用 PowerShell 登录并保留会话：

```powershell
$body = @{ email = 'alice.morgan@example.test'; password = 'DemoPass2026!' } | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:5000/api/login' -Method Post -ContentType 'application/json' -Body $body -SessionVariable apiSession
Invoke-RestMethod 'http://127.0.0.1:5000/api/dashboard' -WebSession $apiSession
```

`POST /api/visits` 可以一次写入到访与店铺评价：提供 `restaurant_id`、`visit_date`、`party_size`、`visibility`，可同时提供 `rating` 和 `review_text`。两条记录在同一事务内提交，失败时一起回滚。`POST /api/plans/{id}/finalize` 会锁定计划、确认投票条件、统计候选餐厅票数并保存胜出餐厅；并列时使用餐厅 ID 较小者。投票触发器也锁定同一计划行，因此投票与确定餐厅不会交错提交。

前端发送 JSON 时可使用以下请求体；日期为 `YYYY-MM-DD`，聚餐时间需包含时区偏移：

```jsonc
// POST /api/friend-requests
{"addressee_id": 7}

// POST /api/visits
{"restaurant_id": 1, "visit_date": "2026-09-27", "party_size": 2, "visibility": "public", "rating": 5, "review_text": "Lovely noodles and welcoming service."}

// POST /api/plans
{"title": "Dinner with friends", "plan_date": "2026-10-11T19:00:00+11:00", "voting_deadline": "2026-10-04T18:00:00+11:00", "candidate_restaurant_ids": [1, 2], "invitee_ids": [2, 3]}
```

上述代码块中的 `//` 仅是示例说明，实际 HTTP 请求体只发送对应的 JSON 对象。错误统一返回 `{"error": "..."}` 与相应 HTTP 状态码。聚餐参与者接受邀请后可调用 `/vote`，发起人可在所有已接受者投票后或投票截止后调用 `/finalize`。

API 对公开、好友可见、私人到访和评论分别执行可见性检查。餐厅公开均分仍来自 `restaurant_rating_summary`，只统计公开评价。Alice 的待处理申请是可实际操作的数据库记录；接受或拒绝后状态会改变。

主机连接参数：`localhost:5433`、数据库 `friend_review`、用户 `friend_app`，密码取自 `.env`。
如果旧终端仍提示找不到 `docker`，请重开终端；本机 Docker CLI 也可通过
`C:\Users\wsq20\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe` 调用。
`sql/init/` 按文件名顺序在**新数据卷首次初始化**时执行。`scripts/catalog.py` 包含人工编写的英文虚构姓名、餐厅、菜单和菜品描述；`scripts/generate_data.py` 用这些素材生成 `05_generated_seed.sql`，并生成语气与评分相符的英文评论、留言及推荐。`06_demo_user1.sql` 把 Alice 的特定演示场景直接写入数据库，不会回滚。当前规模为 **100 个用户、50 家餐厅、250 道菜品、约 1000 次 Visit 和 1000 条店铺 Review**；各店评论数量不完全相同。修改初始化文件不会自动修改已有数据库；已运行的数据库不会因重新执行 `docker compose up` 而重建。

如需**删除本项目现有数据库数据并重新生成**，先运行生成脚本，再执行：

```powershell
docker compose down -v  # 只删除本 Compose 项目的数据库数据卷；其中旧数据不可恢复
docker compose up -d --wait
```

## 与 ER 图的对应

- 实体：`app_user`、`restaurant`、`suburb`、`cuisine`、`visit`、`review`、`review_comment`、`recommendation`、`dining_plan`。
- 菜单扩展：`dish` 记录每家店的菜品、英文介绍、澳元价格与是否供应。它是前端展示用的菜单，不属于原 ER 图的核心实体。
- 多对多或带属性关系：`friendship`、`favorite`、`restaurant_cuisine`（Offer）、`plan_participant`（Attend）、`plan_candidate`（considers）、`plan_vote`（Votes）。
- `Originated_from` 用可选的 `visit.plan_id` 表达；`chosen` 用计划的最终餐厅表达，并限定它必须在该计划候选中。
- 图中的 `Favorite`、`Offer`、`Attend`、`considers` 按“用户可收藏多家餐厅、餐厅可有多个菜系、计划可有多人及多个候选餐厅”的业务含义实现为多对多；若小组决定严格采用图上个别箭头所表达的单一关系，应先修改这份 SQL 与 ER 图，使二者一致。
- 一次 Visit 最多一条 Review；一次 Visit 可以没有 Review。餐厅平均分、评价数用视图计算，不在餐厅实体中重复存储。
- Review 对整家餐厅的一次到访评分，不对菜品单独评分或评论。评论文字可以自然提到点过的菜，但不建立菜品评价关系。
- `Visit.visibility` 控制到店记录及其 Review 的可见范围。`friends` 仅对当下已接受的好友可见；餐厅公开评分只统计 `public` Review。
- 每人对每个计划最多投一票；投票者须已接受邀请，餐厅须是候选项，并且计划处于投票期。
- 推荐只能发送给已接受的好友；关系后来变化不删除历史推荐。

`app_user.password_hash` 保存密码哈希而非明文。初始化数据使用 `pgcrypto` 的加盐 bcrypt，只供演示；样例用户的演示密码是 `DemoPass2026!`。将来若加入应用登录，可以在应用层使用 Argon2id，数据库字段也接受其编码结果。真实用户密码不要写入 SQL 文件。

第一个用户 Alice Morgan（`user_id=1`）是前端演示账号。基础数据在 `04_seed.sql`，补充评价等批量数据在 `05_generated_seed.sql`，好友申请与推荐的特定场景在 `06_demo_user1.sql`。Alice 预置了已接受好友、发出的待处理/被拒申请、来自用户 8 和 9 的待处理申请，以及用户 7 这个可新申请的目标；她还拥有多家收藏餐厅、公开/好友/私人到店评价、收发推荐和参与计划。餐厅评分从 `restaurant_rating_summary` 视图读取。前端可直接读取这些已持久化的数据，再实际执行接受、拒绝、发送等操作；数据库初始化不会替前端执行这些动作。

容器使用 PostgreSQL 17，主机端口为 5433，以避开通常使用 5432 的本机 PostgreSQL。`.env` 已被 Git 忽略。
