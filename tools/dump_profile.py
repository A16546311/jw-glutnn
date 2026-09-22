import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from itsdangerous import URLSafeSerializer  # noqa: E402

import school  # noqa: E402

SECRET = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")
signer = URLSafeSerializer(SECRET, salt="jw-session")
js = signer.loads(open("/tmp/sess.txt").read().strip())["js"]

s = school.new_session(js)

# 顶部栏
r = s.get(school.ACADEMIC + "/showHeader.do", timeout=20)
print("showHeader status:", r.status_code, "len:", len(r.content))
open("/tmp/header.html", "w", encoding="utf-8").write(school.decode(r))

# 学籍信息
try:
    r2 = school.open_module(s, "2060")
    print("module2060 status:", r2.status_code, "len:", len(r2.content), "url:", r2.url)
    open("/tmp/module2060.html", "w", encoding="utf-8").write(school.decode(r2))
except Exception as exc:  # noqa: BLE001
    print("module2060 error:", exc)
