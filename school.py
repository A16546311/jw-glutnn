"""与桂林理工（南宁）教务系统交互的底层客户端。

关键约束（实测结论）：
- 站点为 Apache + 多台 Tomcat，会话粘滞依赖 JSESSIONID 后缀（如 .TD1），
  因此必须原样保留服务端下发的 JSESSIONID。
- 登录密码为客户端算法 submit_hex_md5(pwd) = md5(md5(utf8(pwd)))，小写 hex。
- 页面编码不统一：课表 GBK、成绩 UTF-8，需要按页探测。
- randomString 形如 "Mon Sep 21 14:58:36 CST 2026XXXXXX"，含空格，需 URL 编码。
"""

import datetime
import hashlib
import random
import re

import requests

BASE = "http://jw.glutnn.cn"
ACADEMIC = BASE + "/academic"

LOGIN_PAGE = ACADEMIC + "/common/security/affairLogin.jsp"
CAPTCHA_URL = ACADEMIC + "/getCaptcha.do"
CHECK_CAPTCHA_URL = ACADEMIC + "/checkCaptcha.do"
SECURITY_CHECK_URL = ACADEMIC + "/j_acegi_security_check"
LIST_LEFT_URL = ACADEMIC + "/listLeft.do"
ACCESS_MODULE_URL = ACADEMIC + "/accessModule.do"
WEEKLY_TIMETABLE_URL = ACADEMIC + "/manager/coursearrange/studentWeeklyTimetable.do"

MODULE_SCHEDULE = "2000"   # 本学期课表
MODULE_GRADES = "2021"     # 课程成绩
MODULE_PROFILE = "2060"    # 学籍信息

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TIMEOUT = 20


class SchoolError(Exception):
    pass


class SessionExpired(SchoolError):
    pass


def double_md5(password: str) -> str:
    """复刻原站 submit_hex_md5(pwd, salt)：对 utf8 明文做两轮 MD5，输出小写 hex。"""
    inner = hashlib.md5(password.encode("utf-8")).hexdigest()
    return hashlib.md5(inner.encode("ascii")).hexdigest()


def new_session(jsessionid: str = None) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    if jsessionid:
        s.cookies.set("JSESSIONID", jsessionid, domain="jw.glutnn.cn", path="/academic")
    return s


def decode(resp: requests.Response) -> str:
    """按页面实际编码解码。优先 meta charset，其次 utf-8/gbk 试探。"""
    raw = resp.content
    head = raw[:4096].decode("ascii", "ignore")
    m = re.search(r"charset\s*=\s*[\"']?([\w-]+)", head, re.I)
    if m:
        enc = m.group(1).lower()
        if enc in ("gb2312", "gbk", "gb18030"):
            return raw.decode("gb18030", "replace")
        try:
            return raw.decode(enc, "replace")
        except LookupError:
            pass
    try:
        text = raw.decode("utf-8")
        if "\ufffd" not in text:
            return text
    except UnicodeDecodeError:
        pass
    return raw.decode("gb18030", "replace")


def get_captcha():
    """建立新会话并取回验证码。返回 (jsessionid, image_bytes)。"""
    s = new_session()
    s.get(LOGIN_PAGE, timeout=TIMEOUT)
    r = s.get(
        CAPTCHA_URL,
        params={"captchaCheckCode": "0", "random": str(random.random())},
        timeout=TIMEOUT,
    )
    jsessionid = s.cookies.get("JSESSIONID")
    if not jsessionid:
        raise SchoolError("未能建立会话")
    return jsessionid, r.content


def login(jsessionid: str, username: str, password: str, captcha: str) -> str:
    """提交登录。成功返回新的 jsessionid，失败抛出 SchoolError。"""
    s = new_session(jsessionid)
    try:
        s.post(CHECK_CAPTCHA_URL, params={"captchaCode": captcha}, timeout=TIMEOUT)
    except requests.RequestException:
        pass

    r = s.get(
        SECURITY_CHECK_URL,
        params={
            "j_username": username,
            "j_password": double_md5(password),
            "j_captcha": captcha,
        },
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    location = r.headers.get("Location", "")
    if r.status_code != 302 or "login_error" in location or "affairLogin" in location:
        raise SchoolError("登录失败：账号、密码或验证码不正确")
    return s.cookies.get("JSESSIONID") or jsessionid


def _menu_links(s: requests.Session):
    r = s.get(LIST_LEFT_URL, timeout=TIMEOUT)
    if r.status_code == 302:
        raise SessionExpired("会话已过期，请重新登录")
    html = decode(r)
    links = {}
    for m in re.finditer(r"moduleId=(\d+)&groupId=&randomString=([^\"]+)", html):
        links[m.group(1)] = m.group(2)
    return links


def open_module(s: requests.Session, module_id: str):
    """进入指定模块，返回最终响应（自动跟随 302）。"""
    links = _menu_links(s)
    rs = links.get(str(module_id))
    if not rs:
        raise SchoolError("菜单中未找到模块 %s" % module_id)
    r = s.get(
        ACCESS_MODULE_URL,
        params={"moduleId": str(module_id), "groupId": "", "randomString": rs},
        allow_redirects=True,
        timeout=TIMEOUT,
    )
    if r.status_code == 302:
        raise SessionExpired("会话已过期，请重新登录")
    return r


def fetch_schedule(jsessionid: str) -> str:
    s = new_session(jsessionid)
    return decode(open_module(s, MODULE_SCHEDULE))


def fetch_profile(jsessionid: str) -> str:
    s = new_session(jsessionid)
    return decode(open_module(s, MODULE_PROFILE))


def fetch_grades(jsessionid: str, year: str = "", term: str = "") -> str:
    s = new_session(jsessionid)
    landing = open_module(s, MODULE_GRADES)
    r = s.post(
        landing.url,
        data={
            "year": year,
            "term": term,
            "para": "0",
            "sortColumn": "",
            "Submit": "查询",
        },
        timeout=TIMEOUT,
    )
    if r.status_code == 302:
        raise SessionExpired("会话已过期，请重新登录")
    return decode(r)


def semester_anchor(jsessionid: str, yearid: str, termid: str):
    """求第 1 周周一（datetime.date）。逐周探测课表，取最早日期反推。"""
    s = new_session(jsessionid)
    for week in range(1, 21):
        try:
            r = s.post(
                WEEKLY_TIMETABLE_URL,
                data={"yearid": str(yearid), "termid": str(termid), "whichWeek": str(week)},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            continue
        html = decode(r)
        dates = re.findall(r"(20\d\d)-(\d\d)-(\d\d)", html)
        if not dates:
            continue
        d = min(datetime.date(int(a), int(b), int(c)) for a, b, c in dates)
        return d - datetime.timedelta(days=d.weekday()) - datetime.timedelta(weeks=week - 1)
    return None
