"""生成 Apple 日历可导入的 iCalendar(.ics)。

- 作息使用学校固定大节表（一大节=两小节，40min + 5min 课间）。
- 时间为中国本地浮动时间（无 Z），配合 X-WR-TIMEZONE:Asia/Shanghai。
- 连续周次合并为 RRULE:FREQ=WEEKLY;COUNT=n，非连续周次拆成多个 VEVENT。
"""

from datetime import datetime, timedelta


def _runs(weeks):
    weeks = sorted(set(weeks))
    runs = []
    for w in weeks:
        if runs and w == runs[-1][-1] + 1:
            runs[-1].append(w)
        else:
            runs.append([w])
    return runs


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _esc(text) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """按 RFC5545 折行，保证每行 UTF-8 字节数 <= 75。"""
    if len(line.encode("utf-8")) <= 73:
        return line
    out, chunk = [], line
    while len(chunk.encode("utf-8")) > 73:
        cut = 73
        while cut > 0 and len(chunk[:cut].encode("utf-8")) > 73:
            cut -= 1
        out.append(chunk[:cut])
        chunk = chunk[cut:]
    out.append(chunk)
    return "\r\n ".join(out)


def build_ics(courses, big_periods, anchor_monday, cal_name: str = "课程表", expand: bool = True) -> str:
    """生成 ICS。

    expand=True（默认）：每次课单独一个 VEVENT，兼容性最好、内容最直观；
    expand=False：连续周次用 RRULE:FREQ=WEEKLY;COUNT=n 合并，文件更小。
    """
    by_index = {p["index"]: p for p in big_periods}
    events = []

    for course in courses:
        for meeting in course.get("meetings", []):
            if not meeting.get("weeks") or not meeting.get("day"):
                continue
            big_start = meeting.get("bigIndex")
            big_end = meeting.get("bigEndIndex") or big_start
            if not big_start or big_start not in by_index:
                continue
            start = by_index[big_start]["start"]
            end = by_index.get(big_end, by_index[big_start])["end"]
            sh, sm = [int(x) for x in start.split(":")]
            eh, em = [int(x) for x in end.split(":")]

            groups = [[w] for w in sorted(set(meeting["weeks"]))] if expand else _runs(meeting["weeks"])
            for run in groups:
                d0 = anchor_monday + timedelta(weeks=run[0] - 1, days=meeting["day"] - 1)
                dtstart = datetime(d0.year, d0.month, d0.day, sh, sm)
                dtend = datetime(d0.year, d0.month, d0.day, eh, em)
                weeks_text = ("第%d周" % run[0]) if len(run) == 1 else ("第%d-%d周" % (run[0], run[-1]))
                desc = "教师：%s\n%s\n%s %s\n地点：%s\n课程号：%s" % (
                    course.get("teacher", ""),
                    weeks_text,
                    meeting.get("dayName", ""),
                    meeting.get("period", {}).get("text", ""),
                    meeting.get("room", ""),
                    course.get("code", ""),
                )
                events.append({
                    "dtstart": dtstart,
                    "dtend": dtend,
                    "summary": course.get("name", ""),
                    "location": meeting.get("room", ""),
                    "description": desc,
                    "count": len(run),
                    "uid": "%s-%s-%s-%s-%s@jw-shell" % (
                        course.get("code", "c"),
                        meeting["day"],
                        run[0],
                        start.replace(":", ""),
                        end.replace(":", ""),
                    ),
                })

    events.sort(key=lambda e: (e["dtstart"], e["summary"]))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jw-shell//GLUTNN//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:%s" % _esc(cal_name),
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    stamp = _fmt(datetime.utcnow()) + "Z"
    for e in events:
        lines.append("BEGIN:VEVENT")
        lines.append("UID:%s" % e["uid"])
        lines.append("DTSTAMP:%s" % stamp)
        lines.append("DTSTART:%s" % _fmt(e["dtstart"]))
        lines.append("DTEND:%s" % _fmt(e["dtend"]))
        lines.append("SUMMARY:%s" % _esc(e["summary"]))
        if e["location"]:
            lines.append("LOCATION:%s" % _esc(e["location"]))
        lines.append("DESCRIPTION:%s" % _esc(e["description"]))
        if e["count"] > 1:
            lines.append("RRULE:FREQ=WEEKLY;COUNT=%d" % e["count"])
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
