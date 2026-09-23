"""套壳教务系统：无状态代理后端 + 单页前端。

- 网页端：学校会话(JSESSIONID)经签名后由浏览器持有并回传，服务端不落盘。
- 订阅链接：用一个稳定的签名令牌(绑定用户名)指向内存中的学校会话，
  使 .ics 订阅地址在多次登录间保持不变；服务重启或会话过期后需重新登录。
"""

import base64
import os
import threading
import time

from flask import Flask, Response, jsonify, request
from itsdangerous import URLSafeSerializer

import ics
import parser
import school

app = Flask(__name__, static_folder="static", static_url_path="")

SECRET = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")
_signer = URLSafeSerializer(SECRET, salt="jw-session")
_sub_signer = URLSafeSerializer(SECRET, salt="jw-sub")

# 内存态：用户名 -> {"js": 学校会话, "ts": 时间戳}。仅存会话，不存账号密码。
_sessions = {}
_sessions_lock = threading.Lock()
SESSION_TTL = 8 * 3600


def pack(jsessionid: str) -> str:
    return _signer.dumps({"js": jsessionid})


def unpack(token):
    if not token:
        return None
    try:
        return _signer.loads(token).get("js")
    except Exception:
        return None


def pack_sub(username: str) -> str:
    return _sub_signer.dumps({"u": username})


def unpack_sub(token):
    if not token:
        return None
    try:
        return _sub_signer.loads(token).get("u")
    except Exception:
        return None


def remember(username: str, jsessionid: str):
    with _sessions_lock:
        _sessions[username] = {"js": jsessionid, "ts": time.time()}


def recall(username: str):
    if not username:
        return None
    with _sessions_lock:
        rec = _sessions.get(username)
    if rec and time.time() - rec["ts"] < SESSION_TTL:
        return rec["js"]
    return None


def resolve_session():
    """优先用稳定订阅令牌(sub)，否则用网页端签名会话(session)。"""
    sub = request.args.get("sub")
    if sub:
        return recall(unpack_sub(sub))
    return unpack(request.args.get("session"))


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/captcha")
def api_captcha():
    js, image = school.get_captcha()
    return jsonify({
        "session": pack(js),
        "image": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii"),
    })


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    js = unpack(data.get("session"))
    if not js:
        return jsonify({"ok": False, "error": "会话已失效，请点击验证码刷新后重试"}), 400
    username = str(data.get("username", "")).strip()
    try:
        new_js = school.login(js, username, str(data.get("password", "")), str(data.get("captcha", "")))
    except school.SchoolError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 401
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": "登录异常：%s" % exc}), 502
    remember(username, new_js)
    return jsonify({"ok": True, "session": pack(new_js), "sub": pack_sub(username), "username": username})


@app.get("/api/profile")
def api_profile():
    js = unpack(request.args.get("session"))
    if not js:
        return jsonify({"error": "会话已失效，请重新登录"}), 401
    try:
        return jsonify(parser.parse_profile(school.fetch_profile(js)))
    except school.SessionExpired as exc:
        return jsonify({"error": str(exc)}), 401
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "获取个人信息失败：%s" % exc}), 502


@app.get("/api/schedule")
def api_schedule():
    js = unpack(request.args.get("session"))
    if not js:
        return jsonify({"error": "会话已失效，请重新登录"}), 401
    try:
        data = parser.parse_schedule(school.fetch_schedule(js))
        data["anchorMonday"] = None
        if data.get("yearid") and data.get("termid"):
            anchor = school.semester_anchor(js, data["yearid"], data["termid"])
            if anchor:
                data["anchorMonday"] = anchor.isoformat()
        return jsonify(data)
    except school.SessionExpired as exc:
        return jsonify({"error": str(exc)}), 401
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "获取课表失败：%s" % exc}), 502


@app.get("/api/grades")
def api_grades():
    js = unpack(request.args.get("session"))
    if not js:
        return jsonify({"error": "会话已失效，请重新登录"}), 401
    try:
        html = school.fetch_grades(js, request.args.get("year", ""), request.args.get("term", ""))
        return jsonify({"rows": parser.parse_grades(html)})
    except school.SessionExpired as exc:
        return jsonify({"error": str(exc)}), 401
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "获取成绩失败：%s" % exc}), 502


def _ics_response(js):
    if not js:
        return jsonify({"error": "会话已过期，请在网页端重新登录后再订阅"}), 401
    try:
        data = parser.parse_schedule(school.fetch_schedule(js))
        anchor = None
        if data.get("yearid") and data.get("termid"):
            anchor = school.semester_anchor(js, data["yearid"], data["termid"])
        if not anchor:
            return jsonify({"error": "无法确定学期起始日期，无法生成日历"}), 400
        expand = request.args.get("mode") != "recur"
        body = ics.build_ics(
            data["courses"], data["bigPeriods"], anchor,
            cal_name=data.get("term") or "课程表", expand=expand,
        )
    except school.SessionExpired as exc:
        return jsonify({"error": str(exc)}), 401
    return Response(
        body,
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=schedule.ics"},
    )


@app.get("/api/schedule.ics")
def api_schedule_ics():
    return _ics_response(resolve_session())


@app.get("/calendar/<token>.ics")
def calendar_ics(token):
    """订阅直链：路径以 .ics 结尾，便于日历客户端识别。"""
    return _ics_response(recall(unpack_sub(token)))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
