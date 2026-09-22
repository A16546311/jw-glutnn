import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parser  # noqa: E402

html = open("/tmp/module2060.html", encoding="utf-8").read()
profile = parser.parse_profile(html)
for k, v in profile.items():
    print("%s: %s" % (k, v))
