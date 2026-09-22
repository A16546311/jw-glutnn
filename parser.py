"""教务系统 HTML 解析：课表与成绩。"""

import re

from bs4 import BeautifulSoup

DAY_MAP = {
    "星期一": 1, "周一": 1, "礼拜一": 1,
    "星期二": 2, "周二": 2, "礼拜二": 2,
    "星期三": 3, "周三": 3, "礼拜三": 3,
    "星期四": 4, "周四": 4, "礼拜四": 4,
    "星期五": 5, "周五": 5, "礼拜五": 5,
    "星期六": 6, "周六": 6, "礼拜六": 6,
    "星期日": 7, "星期天": 7, "周日": 7, "周天": 7, "礼拜日": 7, "礼拜天": 7,
}

DAY_NAME = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}

# 学校固定作息：一大节含两小节，每小节 40 分钟，小节间课间 5 分钟。
BIG_PERIODS = [
    {"index": 1, "name": "第1-2节", "start": "08:40", "end": "10:05", "part": "上午"},
    {"index": 2, "name": "第3-4节", "start": "10:25", "end": "11:50", "part": "上午"},
    {"index": 3, "name": "第5-6节", "start": "14:30", "end": "15:55", "part": "下午"},
    {"index": 4, "name": "第7-8节", "start": "16:05", "end": "17:30", "part": "下午"},
    {"index": 5, "name": "第9-10节", "start": "19:30", "end": "20:55", "part": "晚上"},
]


def big_period_range(period):
    """把「第7-8节」映射到大节序号。返回 (起始大节, 结束大节)。"""
    if not period:
        return None, None
    start = max(1, min(5, (period["start"] + 1) // 2))
    end = max(1, min(5, (period["end"] + 1) // 2))
    if end < start:
        end = start
    return start, end


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _text(node) -> str:
    return _norm(node.get_text(" ", strip=True)) if node else ""


def _direct_rows(table):
    """只取表格自身的行，不进入嵌套子表格。"""
    rows = []

    def walk(node):
        for child in node.find_all(["tr", "tbody", "thead", "tfoot"], recursive=False):
            if child.name == "tr":
                rows.append(child)
            else:
                walk(child)

    walk(table)
    return rows


def parse_weeks(text: str):
    """解析周次表达式，返回升序周号列表。

    支持：9-16周 / 6周 / 1-2,4-6 / 第4周 / 第1-2周 / 1,4-6 / 单周 / 双周
    """
    if not text:
        return []
    t = text.replace("第", "").replace("周", "").replace(" ", "")
    odd = "单" in t
    even = "双" in t
    t = t.replace("单", "").replace("双", "")
    weeks = set()
    for part in re.split(r"[,，、]", t):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            weeks.update(range(a, b + 1))
            continue
        m = re.match(r"^(\d+)$", part)
        if m:
            weeks.add(int(m.group(1)))
    result = sorted(weeks)
    if odd:
        result = [w for w in result if w % 2 == 1]
    if even:
        result = [w for w in result if w % 2 == 0]
    return result


def expand_weeks_text(weeks):
    """把周号列表压缩成人类可读文本，如 [1,2,4,5,6] -> '第1-2、4-6周'。"""
    if not weeks:
        return ""
    weeks = sorted(set(weeks))
    runs = []
    for w in weeks:
        if runs and w == runs[-1][-1] + 1:
            runs[-1].append(w)
        else:
            runs.append([w])
    parts = []
    for run in runs:
        parts.append(str(run[0]) if len(run) == 1 else "%d-%d" % (run[0], run[-1]))
    return "第" + "、".join(parts) + "周"


def parse_day(text: str):
    t = _norm(text)
    for key, value in DAY_MAP.items():
        if key in t:
            return value
    return None


def parse_period(text: str):
    nums = [int(x) for x in re.findall(r"\d+", text or "")]
    if not nums:
        return None
    return {"start": nums[0], "end": nums[-1], "text": _norm(text)}


def parse_periods(table):
    """解析「上课大节」表：节次名称 -> 真实起止时间。"""
    periods = {}
    if table is None:
        return periods
    for tr in _direct_rows(table):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        name = _norm(tds[1].get_text())
        timecell = tds[-1].get_text(" ", strip=True)
        times = re.findall(r"(\d{1,2}):(\d{2})(?::\d{2})?", timecell)
        if len(times) >= 2:
            periods[name] = {
                "start": "%02d:%s" % (int(times[0][0]), times[0][1]),
                "end": "%02d:%s" % (int(times[-1][0]), times[-1][1]),
            }
    return periods


def parse_meetings(cell):
    meetings = []
    if cell is None:
        return meetings
    for tr in cell.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        weeks_text = tds[0].get_text(strip=True)
        weeks = parse_weeks(weeks_text)
        if not weeks:
            continue
        day = parse_day(tds[1].get_text(strip=True))
        period = parse_period(tds[2].get_text(strip=True))
        room = tds[3].get_text(strip=True)
        if room in ("&nbsp;", "\xa0"):
            room = ""
        big_start, big_end = big_period_range(period)
        meetings.append({
            "weeksText": weeks_text,
            "weeks": weeks,
            "weeksReadable": expand_weeks_text(weeks),
            "weekCount": len(weeks),
            "day": day,
            "dayName": DAY_NAME.get(day, ""),
            "period": period,
            "bigIndex": big_start,
            "bigEndIndex": big_end,
            "room": room,
        })
    return meetings


def parse_schedule(html: str):
    soup = BeautifulSoup(html, "lxml")
    tables = soup.select("table.infolist_tab")
    periods = parse_periods(tables[-1]) if len(tables) >= 2 else {}

    yearid = termid = None
    m = re.search(r"yearid=(\d+)&termid=(\d+)", html)
    if m:
        yearid, termid = m.group(1), m.group(2)

    term_title = ""
    title = soup.select_one("table#title")
    if title:
        term_title = _norm(title.get_text())

    courses = []
    if tables:
        table = tables[0]
        ths = [_norm(th.get_text()) for th in table.find_all("th")]

        def col(*names):
            for i, h in enumerate(ths):
                for n in names:
                    if n in h:
                        return i
            return -1

        i_code = col("课程号")
        i_name = col("课程名称", "课程名")
        i_teacher = col("任课教师", "教师")
        i_credit = col("学分")
        i_prop = col("选课属性")
        i_time = col("上课时间")

        for tr in _direct_rows(table):
            tds = tr.find_all("td", recursive=False)
            if not tds or len(tds) < 2:
                continue

            def cell(i):
                return tds[i] if 0 <= i < len(tds) else None

            name = _text(cell(i_name))
            if not name:
                continue
            teachers = []
            teacher_cell = cell(i_teacher)
            if teacher_cell:
                teachers = [
                    _norm(a.get_text())
                    for a in teacher_cell.find_all("a")
                    if _norm(a.get_text())
                ] or [_text(teacher_cell)]
            courses.append({
                "code": _text(cell(i_code)),
                "name": name,
                "teachers": teachers,
                "teacher": "、".join(t for t in teachers if t),
                "credit": _text(cell(i_credit)),
                "prop": _text(cell(i_prop)),
                "meetings": parse_meetings(cell(i_time)),
            })

    return {
        "term": term_title,
        "yearid": yearid,
        "termid": termid,
        "periods": periods,
        "bigPeriods": BIG_PERIODS,
        "courses": courses,
    }


def parse_grades(html: str):
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.datalist")
    if table is None:
        return []
    ths = [_norm(th.get_text()) for th in table.find_all("th")]
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not ths or len(tds) < len(ths):
            continue
        values = [_norm(td.get_text()) for td in tds]
        rows.append(dict(zip(ths, values)))
    return rows


# 学籍信息中对外展示的字段（不含证件号、电话等敏感项）
PROFILE_FIELDS = [
    "姓名", "学号", "性别", "出生日期", "民族", "政治面貌",
    "院系", "专业", "年级", "班级", "学生类别", "校区",
    "学生当前状态", "入学日期",
]


def parse_profile(html: str):
    """解析学籍信息页的隐藏字段表，返回 {字段: 值}。"""
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form", attrs={"name": "studentModifyInfoAcquireFillForm"}) or soup
    data = {}
    for table in form.find_all("table", class_="form"):
        for tr in _direct_rows(table):
            cells = tr.find_all(["th", "td"], recursive=False)
            i = 0
            while i < len(cells):
                if (cells[i].name == "th" and i + 1 < len(cells)
                        and cells[i + 1].name == "td"):
                    label = _norm(cells[i].get_text())
                    value = _norm(cells[i + 1].get_text())
                    if label and label not in data:
                        data[label] = value
                    i += 2
                else:
                    i += 1
    profile = {field: data.get(field, "") for field in PROFILE_FIELDS}

    # 学号/姓名兜底：从顶部问候语取
    m = re.search(r"您好！\s*([^（(]+)[（(](\d+)[)）]", html)
    if m:
        profile["姓名"] = profile.get("姓名") or _norm(m.group(1))
        profile["学号"] = profile.get("学号") or m.group(2)
    return profile

