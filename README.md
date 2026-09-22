# 桂林理工南宁分校教务套壳（jw-shell）

-原因是wakeup付费还有广告,课表解析常常一团糟.遂尝试很火的"超级课程表",这位更是重量级,点一下"假期中"切换学期之间跳去美团订假期酒店,
日常广告更是多不胜数,稍有不慎就转跳到了jd/胆子肥嘟嘟袋鼠
-把桂林理工大学（南宁）综合教务管理系统 `jw.glutnn.cn` 套一层自建网页：
代理登录、解析成绩与课表、按周格子展示课表、导出 Apple 日历（.ics）并支持订阅。

> 数据全部实时从原教务系统解析，**一切以原教务系统页面为准**。

---

## 功能

- **登录代理**：透传原登录页的用户名 / 密码 / 验证码，触发浏览器密码填充；服务端不保存账号密码。
- **个人信息**：左侧栏展示姓名、学号、院系、专业、班级、年级、校区、学籍状态（来自「学籍信息」模块）。
- **本学期进度**：按第 1 周周一推算当前周次与进度条。
- **课表**：解析「本学期课表」，按大节作息渲染**按周格子视图**，可切换列表视图（周次自动展开）。
- **成绩**：解析「课程成绩」，支持按学年 / 学期筛选，自动统计学分（绩点计算规则暂不明确，暂不计算）。
- **日历导出**：生成 `.ics`（连续周次合并为 `RRULE`，单双周/断续周次自动拆段）。
- **日历订阅**：稳定的订阅链接，可加入 Apple 日历。

## 快速开始

### 方式一：Docker（推荐）

```bash
tar -xzf jw-shell.tar.gz && cd jw-shell
# 修改 docker-compose.yml 中的 SECRET_KEY 为随机串
docker compose up -d --build
# 浏览器打开 http://<主机IP>:8000
```

### 方式二：本地运行（Python 3.10+）

```bash
cd jw-shell
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py            # 监听 0.0.0.0:8000
```

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SECRET_KEY` | `dev-insecure-secret-change-me` | 会话签名密钥，**生产必须修改**；多 worker/多副本需一致 |
| `PORT` | `8000` | 监听端口（`python app.py` 时生效） |
| `TZ` | `Asia/Shanghai` | 时区 |

---

## 框架构成

```
jw-shell/
├── app.py                  Flask 入口：路由、签名会话、订阅令牌、内存会话表
├── school.py               与教务系统交互（登录、菜单、课表、成绩、学籍、周次锚点）
├── parser.py               HTML 解析（课表 / 成绩 / 个人信息、周次展开、大节映射）
├── ics.py                  iCalendar(.ics) 生成
├── static/
│   ├── index.html          单页界面
│   ├── app.js              前端逻辑（登录、格子课表、成绩、侧栏）
│   └── style.css           样式
├── tools/                  本地调试脚本（cli.py / test_parsers.py 等，生产可删）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .dockerignore
```

技术栈：**Python + Flask + requests + BeautifulSoup(lxml)**；前端为原生 JS 单页，无构建步骤。

### 模块职责

| 文件 | 职责 |
|---|---|
| `school.py` | 会话管理、验证码、登录、菜单解析、`accessModule` 跳转、抓取课表/成绩/学籍、求学期第 1 周周一 |
| `parser.py` | `parse_schedule` / `parse_grades` / `parse_profile`；`parse_weeks` 周次展开；`BIG_PERIODS` 大节作息 |
| `ics.py` | `build_ics`：按大节时间与周次生成 VEVENT（RRULE 合并连续周） |
| `app.py` | `/api/*` 接口；签名会话；订阅令牌与内存会话表 |

### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/captcha` | 取验证码图片(base64) + 会话令牌 |
| POST | `/api/login` | 登录，返回网页会话令牌与订阅令牌 |
| GET | `/api/profile?session=` | 个人信息 |
| GET | `/api/schedule?session=` | 课表（含大节表、学期锚点） |
| GET | `/api/grades?session=` | 成绩列表 |
| GET | `/api/schedule.ics?session=` | 下载 .ics |
| GET | `/api/schedule.ics?sub=` | 订阅用 .ics（稳定令牌） |

---

## 工作原理（关键实现点）

1. **登录密码**：原站为客户端算法 `submit_hex_md5(pwd)`，等价于 `md5(md5(utf8(明文)))` 的小写 hex。
2. **会话粘滞**：校方为 Apache + 多台 Tomcat，`JSESSIONID` 后缀（如 `.TD1`）决定路由；必须原样保留服务端下发的 `JSESSIONID`，否则每次请求新建会话、验证码永远不通过。
3. **页面编码不统一**：课表页 GBK、成绩页 UTF-8，按页探测解码。
4. **模块入口**：`listLeft.do` 解析出 `moduleId` 与一次性 `randomString`，再经 `accessModule.do` 跳转（课表 2000 → `currcourse.jsdo`；成绩 2021 → `studentOwnScore.do`）。
5. **大节作息**：一大节含两小节，每小节 40 分钟、课间 5 分钟：
   第1-2节 08:40–10:05 / 第3-4节 10:25–11:50 / 第5-6节 14:30–15:55 / 第7-8节 16:05–17:30 / 第9-10节 19:30–20:55。
6. **学期锚点**：由 `studentWeeklyTimetable.do` 逐周探测最早日期反推第 1 周周一，用于把周次换算成真实日期。
7. **订阅链接**：`sub` 为绑定用户名的签名令牌，指向**内存**中的学校会话（TTL 8 小时）。因登录需验证码，服务端无法自动续登；学校会话过期后，在网页端重新登录即可让同一订阅链接恢复。

## 免责声明

- 本项目数据均由原教务系统实时解析，仅供参考；**一切以原教务系统页面为准**。
- 导出的日历、成绩等信息请在原教务系统**核对无误后**再使用。
- 本项目与学校官方无关，使用风险自负。
- 服务端不保存账号密码；但仍请妥善保管访问地址与订阅链接。
