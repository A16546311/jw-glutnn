"""本地端到端调试工具：与本机运行中的服务交互。

用法:
  cli.py captcha          取验证码 -> /tmp/cap.png 与 /tmp/sess.txt
  cli.py login <验证码>    登录 -> 更新 /tmp/sess.txt
  cli.py schedule         取课表 -> /tmp/schedule.json
  cli.py grades           取成绩 -> /tmp/grades.json
  cli.py ics              取日历 -> /tmp/schedule.ics
"""

import base64
import json
import os
import sys
import urllib.parse
import urllib.request

PORT = os.environ.get("JW_PORT", "8000")
BASE = "http://127.0.0.1:%s" % PORT
SESS = "/tmp/sess.txt"


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as resp:
        return resp.read()


def _post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_session():
    with open(SESS) as fh:
        return fh.read().strip()


def save_session(token):
    with open(SESS, "w") as fh:
        fh.write(token)


def cmd_captcha():
    data = json.loads(_get("/api/captcha").decode("utf-8"))
    raw = base64.b64decode(data["image"].split(",", 1)[1])
    with open("/tmp/cap.png", "wb") as fh:
        fh.write(raw)
    save_session(data["session"])
    print("captcha saved -> /tmp/cap.png (%d bytes)" % len(raw))


def cmd_login(code):
    data = _post("/api/login", {
        "session": load_session(),
        "username": os.environ.get("JW_USER", ""),
        "password": os.environ.get("JW_PASS", ""),
        "captcha": code,
    })
    if not data.get("ok"):
        print("LOGIN FAILED:", data.get("error"))
        sys.exit(1)
    save_session(data["session"])
    if data.get("sub"):
        with open("/tmp/sub.txt", "w") as fh:
            fh.write(data["sub"])
    print("login ok")


def cmd_schedule():
    q = urllib.parse.urlencode({"session": load_session()})
    body = _get("/api/schedule?" + q)
    with open("/tmp/schedule.json", "wb") as fh:
        fh.write(body)
    data = json.loads(body)
    print("schedule: %d courses -> /tmp/schedule.json" % len(data.get("courses", [])))


def cmd_grades():
    q = urllib.parse.urlencode({"session": load_session()})
    body = _get("/api/grades?" + q)
    with open("/tmp/grades.json", "wb") as fh:
        fh.write(body)
    data = json.loads(body)
    print("grades: %d rows -> /tmp/grades.json" % len(data.get("rows", [])))


def cmd_ics():
    q = urllib.parse.urlencode({"session": load_session()})
    body = _get("/api/schedule.ics?" + q)
    with open("/tmp/schedule.ics", "wb") as fh:
        fh.write(body)
    print("ics: %d bytes -> /tmp/schedule.ics" % len(body))


def cmd_profile():
    q = urllib.parse.urlencode({"session": load_session()})
    body = _get("/api/profile?" + q)
    with open("/tmp/profile.json", "wb") as fh:
        fh.write(body)
    print(body.decode("utf-8"))


def cmd_sub():
    print("subscription url path: /api/schedule.ics?sub=" + load_session())


def cmd_ics_sub():
    sub = open("/tmp/sub.txt").read().strip()
    q = urllib.parse.urlencode({"sub": sub})
    body = _get("/api/schedule.ics?" + q)
    with open("/tmp/schedule_sub.ics", "wb") as fh:
        fh.write(body)
    print("ics(sub): %d bytes -> /tmp/schedule_sub.ics" % len(body))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    action = sys.argv[1]
    if action == "captcha":
        cmd_captcha()
    elif action == "login":
        cmd_login(sys.argv[2])
    elif action == "schedule":
        cmd_schedule()
    elif action == "grades":
        cmd_grades()
    elif action == "ics":
        cmd_ics()
    elif action == "profile":
        cmd_profile()
    elif action == "ics-sub":
        cmd_ics_sub()
    else:
        print(__doc__)
        sys.exit(1)
