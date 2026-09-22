"""离线验证解析器与 ICS 生成（使用真实页面样本）。"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ics  # noqa: E402
import parser  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), "samples")


def main():
    with open(os.path.join(SAMPLES, "schedule.html"), encoding="utf-8") as fh:
        schedule_html = fh.read()
    data = parser.parse_schedule(schedule_html)

    print("学期:", data["term"], "| yearid:", data["yearid"], "termid:", data["termid"])
    print("大节数:", len(data["periods"]), "| 课程数:", len(data["courses"]))
    print("第7-8节时间:", data["periods"].get("第7-8节"))
    print("-" * 60)
    for course in data["courses"][:3]:
        print(course["name"], "|", course["teacher"], "|", course["credit"], "学分")
        for meeting in course["meetings"]:
            print("   ", meeting["dayName"], meeting["period"]["text"] if meeting["period"] else "",
                  meeting["room"], "->", meeting["weeksReadable"], "共", meeting["weekCount"], "周")

    anchor = datetime.date(2026, 9, 7)
    body = ics.build_ics(data["courses"], data["bigPeriods"], anchor, cal_name=data["term"])
    events = body.count("BEGIN:VEVENT")
    print("-" * 60)
    print("ICS 事件数:", events, "| 字节:", len(body.encode("utf-8")))
    print("首个 VEVENT 片段:")
    start = body.index("BEGIN:VEVENT")
    print(body[start:start + 260])

    with open(os.path.join(SAMPLES, "grades.html"), encoding="utf-8") as fh:
        grades_html = fh.read()
    rows = parser.parse_grades(grades_html)
    print("-" * 60)
    print("成绩条数:", len(rows))
    for row in rows[:3]:
        print("  ", row.get("学年"), row.get("学期"), row.get("课程名"), row.get("总评"), row.get("绩点"))


if __name__ == "__main__":
    main()
