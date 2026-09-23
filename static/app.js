"use strict";

const state = {
  session: null,
  sub: null,
  profile: null,
  schedule: null,
  grades: null,
  week: 1,
  view: "grid",
};

const $ = (sel) => document.querySelector(sel);

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}

/* ---------- 登录 ---------- */

async function loadCaptcha() {
  const data = await api("/api/captcha");
  state.session = data.session;
  $("#captcha-img").src = data.image;
}

$("#captcha-img").addEventListener("click", () => {
  loadCaptcha().catch((e) => setMsg(e.message));
});

function setMsg(text, ok) {
  const el = $("#login-msg");
  el.textContent = text || "";
  el.className = "msg" + (ok ? " ok" : text ? " err" : "");
}

$("#login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const btn = $("#login-btn");
  btn.disabled = true;
  setMsg("登录中…");
  try {
    const data = await api("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session: state.session,
        username: $("#username").value.trim(),
        password: $("#password").value,
        captcha: $("#captcha").value.trim(),
      }),
    });
    state.session = data.session;
    state.sub = data.sub;
    showMain();
  } catch (err) {
    setMsg(err.message);
    loadCaptcha().catch(() => {});
  } finally {
    btn.disabled = false;
  }
});

function showMain() {
  $("#login-view").classList.add("hidden");
  $("#main-view").classList.remove("hidden");
  setupSub();
  loadProfile();
  loadSchedule();
}

$("#logout").addEventListener("click", () => {
  state.session = null;
  state.sub = null;
  state.profile = null;
  state.schedule = null;
  state.grades = null;
  state.week = 1;
  $("#main-view").classList.add("hidden");
  $("#login-view").classList.remove("hidden");
  $("#password").value = "";
  $("#captcha").value = "";
  setMsg("");
  loadCaptcha().catch(() => {});
});

/* ---------- 左侧栏：个人信息 / 进度 / 订阅 ---------- */

async function loadProfile() {
  try {
    state.profile = await api("/api/profile?session=" + encodeURIComponent(state.session));
    renderProfile();
  } catch (err) {
    $("#profile-card").innerHTML = '<div class="error">' + escapeHtml(err.message) + "</div>";
  }
}

function renderProfile() {
  const p = state.profile || {};
  const name = p["姓名"] || "同学";
  const rows = [
    ["学号", p["学号"]],
    ["院系", p["院系"]],
    ["专业", p["专业"]],
    ["班级", p["班级"]],
    ["年级", p["年级"]],
    ["学生类别", p["学生类别"]],
    ["校区", p["校区"]],
    ["当前状态", p["学生当前状态"]],
  ].filter((r) => r[1]);

  let html = '<div class="profile-head">';
  html += '<div class="avatar">' + escapeHtml(name.slice(0, 1)) + "</div>";
  html += '<div><div class="pname">' + escapeHtml(name) + "</div>";
  html += '<div class="pmeta">' + escapeHtml(p["学号"] || "") + "</div></div>";
  html += "</div><dl class=\"profile-list\">";
  rows.forEach(([k, v]) => {
    html += "<dt>" + escapeHtml(k) + "</dt><dd>" + escapeHtml(v) + "</dd>";
  });
  html += "</dl>";
  $("#profile-card").innerHTML = html;
}

function renderProgress() {
  const el = $("#progress-card");
  const data = state.schedule;
  if (!data || !data.anchorMonday) {
    el.innerHTML = "";
    return;
  }
  const anchor = parseAnchor(data.anchorMonday);
  let maxWeek = 0;
  (data.courses || []).forEach((c) => (c.meetings || []).forEach((m) =>
    (m.weeks || []).forEach((w) => { if (w > maxWeek) maxWeek = w; })));
  if (!maxWeek) maxWeek = 19;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dayDiff = Math.floor((today - anchor) / 86400000);
  const week = Math.floor(dayDiff / 7) + 1;
  const end = new Date(anchor.getTime());
  end.setDate(end.getDate() + maxWeek * 7 - 1);

  let status = "进行中";
  let pct = Math.round((Math.min(Math.max(week, 0), maxWeek) / maxWeek) * 100);
  if (dayDiff < 0) { status = "未开学"; pct = 0; }
  else if (week > maxWeek) { status = "已结束"; pct = 100; }

  let html = '<h3>本学期进度</h3>';
  html += '<div class="prog-top"><span class="prog-week">第 ' +
    Math.max(week, 0) + " / " + maxWeek + ' 周</span><span class="prog-status">' + status + "</span></div>";
  html += '<div class="bar"><i style="width:' + pct + '%"></i></div>';
  html += '<div class="tiny">' + fmtDate(anchor) + " ~ " + fmtDate(end) + "</div>";
  el.innerHTML = html;
}

function setupSub() {
  const url = location.origin + "/calendar/" + state.sub + ".ics";
  $("#sub-url").value = url;
  $("#webcal-link").href = url.replace(/^https?:/, "webcal:");
  $("#copy-sub").onclick = async () => {
    try {
      await navigator.clipboard.writeText(url);
      $("#copy-sub").textContent = "已复制";
      setTimeout(() => { $("#copy-sub").textContent = "复制链接"; }, 1500);
    } catch (e) {
      $("#sub-url").select();
      document.execCommand("copy");
    }
  };
}

/* ---------- Tab ---------- */

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    $("#tab-schedule").classList.toggle("hidden", tab !== "schedule");
    $("#tab-grades").classList.toggle("hidden", tab !== "grades");
    if (tab === "grades" && !state.grades) loadGrades();
  });
});

/* ---------- 课表 ---------- */

async function loadSchedule() {
  const body = $("#schedule-body");
  body.innerHTML = '<div class="loading">正在获取课表…</div>';
  try {
    const data = await api("/api/schedule?session=" + encodeURIComponent(state.session));
    state.schedule = data;
    state.week = 1;
    renderSchedule();
  } catch (err) {
    body.innerHTML = '<div class="error">' + escapeHtml(err.message) + "</div>";
  }
}

function dateFromAnchor(anchor, week, day) {
  const d = new Date(anchor.getTime());
  d.setDate(d.getDate() + (week - 1) * 7 + (day - 1));
  return d;
}

function fmtMD(d) {
  return String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

function fmtDate(d) {
  return d.getFullYear() + "-" + fmtMD(d);
}

function parseAnchor(s) {
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function renderSchedule() {
  const data = state.schedule;
  if (!data) return;
  $("#term-title").textContent = data.term || "";
  renderProgress();

  const body = $("#schedule-body");
  if (!data.courses || !data.courses.length) {
    body.innerHTML = '<div class="error">没有查到课程。</div>';
    return;
  }

  const anchor = parseAnchor(data.anchorMonday);
  let maxWeek = 0;
  const daySet = new Set();
  data.courses.forEach((c) => (c.meetings || []).forEach((m) => {
    (m.weeks || []).forEach((w) => { if (w > maxWeek) maxWeek = w; });
    if (m.day) daySet.add(m.day);
  }));
  if (!maxWeek) maxWeek = 19;
  const days = daySet.size ? [...daySet].sort((a, b) => a - b) : [1, 2, 3, 4, 5];

  let html = '<div class="weekbar">';
  html += '<button id="prev-week" class="ghost">‹</button>';
  html += '<select id="week-select">';
  for (let w = 1; w <= maxWeek; w++) {
    html += '<option value="' + w + '"' + (w === state.week ? " selected" : "") + ">第 " + w + " 周</option>";
  }
  html += "</select>";
  html += '<button id="next-week" class="ghost">›</button>';
  html += '<span class="week-range" id="week-range"></span>';
  html += '<span class="spacer"></span>';
  html += '<button id="view-toggle" class="ghost">' + (state.view === "grid" ? "列表视图" : "格子视图") + "</button>";
  html += "</div>";
  html += '<div id="schedule-view"></div>';
  body.innerHTML = html;

  $("#prev-week").onclick = () => { if (state.week > 1) { state.week--; renderSchedule(); } };
  $("#next-week").onclick = () => { if (state.week < maxWeek) { state.week++; renderSchedule(); } };
  $("#week-select").onchange = (e) => { state.week = parseInt(e.target.value, 10); renderSchedule(); };
  $("#view-toggle").onclick = () => { state.view = state.view === "grid" ? "list" : "grid"; renderSchedule(); };

  const monday = anchor ? dateFromAnchor(anchor, state.week, 1) : null;
  const sunday = anchor ? dateFromAnchor(anchor, state.week, 7) : null;
  $("#week-range").textContent = monday ? "（" + fmtMD(monday) + " ~ " + fmtMD(sunday) + "）" : "";

  if (state.view === "grid") {
    renderGrid(data, days, anchor);
  } else {
    renderList(data);
  }
}

function renderGrid(data, days, anchor) {
  const bigPeriods = data.bigPeriods || [];
  const week = state.week;

  let html = '<div class="grid-wrap"><table class="grid"><thead><tr>';
  html += '<th class="corner">节次 / 星期</th>';
  days.forEach((d) => {
    const date = anchor ? fmtMD(dateFromAnchor(anchor, week, d)) : "";
    html += '<th><div class="dname">' + DAY_NAME(d) + '</div><div class="ddate">' + date + "</div></th>";
  });
  html += "</tr></thead><tbody>";

  bigPeriods.forEach((bp) => {
    html += '<tr><th class="period"><div class="pname">' + escapeHtml(bp.name) + '</div>' +
      '<div class="ptime">' + bp.start + "-" + bp.end + "</div></th>";
    days.forEach((d) => {
      const blocks = [];
      data.courses.forEach((c) => {
        (c.meetings || []).forEach((m) => {
          if (m.day !== d || !m.weeks.includes(week)) return;
          const bs = m.bigIndex || 0;
          const be = m.bigEndIndex || bs;
          if (bp.index < bs || bp.index > be) return;
          blocks.push({ c, m });
        });
      });
      html += "<td>";
      blocks.forEach(({ c, m }) => {
        html += '<div class="block" title="' + escapeHtml(c.name + " " + (m.room || "")) + '">';
        html += '<div class="bname">' + escapeHtml(shortName(c.name)) + "</div>";
        if (m.room) html += '<div class="broom">' + escapeHtml(m.room) + "</div>";
        if (c.teacher) html += '<div class="bteacher">' + escapeHtml(c.teacher) + "</div>";
        html += "</div>";
      });
      html += "</td>";
    });
    html += "</tr>";
  });
  html += "</tbody></table></div>";
  $("#schedule-view").innerHTML = html;
}

function renderList(data) {
  const anchor = parseAnchor(data.anchorMonday);
  let html = '<p class="sub">共 ' + data.courses.length + " 门课" +
    (anchor ? "（第 1 周周一：" + data.anchorMonday + "）" : "") + "</p>";
  data.courses.forEach((course) => {
    html += '<div class="course"><div class="course-head"><span class="cname">' + escapeHtml(course.name) + "</span>";
    const meta = [];
    if (course.teacher) meta.push(course.teacher);
    if (course.credit) meta.push(course.credit + " 学分");
    if (course.prop) meta.push(course.prop);
    if (course.code) meta.push(course.code);
    html += '<span class="cmeta">' + escapeHtml(meta.join(" · ")) + "</span></div>";
    if (!course.meetings.length) {
      html += '<div class="muted">未安排上课时间（如实习/设计类）</div>';
    } else {
      html += '<ul class="meetings">';
      course.meetings.slice().sort((a, b) =>
        (a.day || 9) - (b.day || 9) ||
        ((a.period && a.period.start) || 99) - ((b.period && b.period.start) || 99)
      ).forEach((m) => {
        const parts = [];
        if (m.dayName) parts.push(m.dayName);
        if (m.period) parts.push(m.period.text);
        if (m.room) parts.push(m.room);
        html += '<li><span class="slot">' + escapeHtml(parts.join(" ")) + "</span>" +
          '<span class="weeks">' + escapeHtml(m.weeksReadable) +
          "（共 " + m.weeks.length + " 周：" + m.weeks.join("、") + " 周）</span></li>";
      });
      html += "</ul>";
    }
    html += "</div>";
  });
  $("#schedule-view").innerHTML = html;
}

const DAY_CN = { 1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日" };
function DAY_NAME(d) { return DAY_CN[d] || ("周" + d); }

function shortName(name) {
  return name.length > 12 ? name.slice(0, 12) + "…" : name;
}

$("#ics-btn").addEventListener("click", () => {
  if (!state.session) return;
  window.location.href = "/api/schedule.ics?session=" + encodeURIComponent(state.session);
});

/* ---------- 成绩 ---------- */

async function loadGrades() {
  const body = $("#grades-body");
  body.innerHTML = '<div class="loading">正在获取成绩…</div>';
  try {
    const data = await api("/api/grades?session=" + encodeURIComponent(state.session));
    state.grades = data.rows || [];
    buildGradeFilters();
    renderGrades();
  } catch (err) {
    body.innerHTML = '<div class="error">' + escapeHtml(err.message) + "</div>";
  }
}

function buildGradeFilters() {
  const years = [...new Set(state.grades.map((r) => r["学年"]))].filter(Boolean).sort().reverse();
  const terms = [...new Set(state.grades.map((r) => r["学期"]))].filter(Boolean);
  const y = $("#grade-year");
  const t = $("#grade-term");
  y.innerHTML = '<option value="">全部</option>' + years.map((v) => "<option>" + escapeHtml(v) + "</option>").join("");
  t.innerHTML = '<option value="">全部</option>' + terms.map((v) => "<option>" + escapeHtml(v) + "</option>").join("");
  y.onchange = renderGrades;
  t.onchange = renderGrades;
}

function renderGrades() {
  const body = $("#grades-body");
  const year = $("#grade-year").value;
  const term = $("#grade-term").value;
  const rows = state.grades.filter(
    (r) => (!year || r["学年"] === year) && (!term || r["学期"] === term)
  );

  let credits = 0;
  rows.forEach((r) => {
    const c = parseFloat(r["学分"]);
    if (!isNaN(c)) credits += c;
  });
  $("#grade-summary").textContent = "共 " + rows.length + " 条 · 学分 " +
    (Math.round(credits * 100) / 100);

  if (!rows.length) {
    body.innerHTML = '<div class="error">没有成绩记录。</div>';
    return;
  }
  const cols = ["学年", "学期", "课程号", "课程名", "主讲教师", "总评", "绩点", "学分", "课程类别", "及格标志"];
  let html = '<table class="grades"><thead><tr>' +
    cols.map((c) => "<th>" + escapeHtml(c) + "</th>").join("") + "</tr></thead><tbody>";
  rows.forEach((r) => {
    const pass = r["及格标志"] || "";
    const cls = pass.includes("不及格") || pass.includes("否") ? "fail" : "";
    html += "<tr>" + cols.map((c) => {
      const val = r[c] == null ? "" : r[c];
      return '<td class="' + (c === "课程名" ? "name " : "") + cls + '">' + escapeHtml(val) + "</td>";
    }).join("") + "</tr>";
  });
  html += "</tbody></table>";
  body.innerHTML = html;
}

/* ---------- utils ---------- */

function escapeHtml(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

loadCaptcha().catch((e) => setMsg(e.message));
