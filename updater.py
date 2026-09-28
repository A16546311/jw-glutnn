"""OTA 自更新：从远程仓库拉取新版本并热重载。

- 版本判定：比较本地 VERSION 与远程仓库 raw VERSION。
- 更新方式：下载分支 tarball 覆盖应用目录（保留用户配置），必要时重装依赖，然后重启服务。
- 重启：gunicorn 下向 master 发 SIGHUP 热重载；其它情况用 os.execv 自重启。
"""

import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))

REPO = os.environ.get("UPDATE_REPO", "A16546311/jw-glutnn")
BRANCH = os.environ.get("UPDATE_BRANCH", "main")
ENABLED = os.environ.get("UPDATE_ENABLED", "1").lower() not in ("0", "false", "no", "")
TOKEN = os.environ.get("UPDATE_TOKEN", "")

STATE_FILE = os.path.join(APP_DIR, ".ota_state.json")
BACKUP_DIR = os.path.join(APP_DIR, ".ota_backup")
VERSION_FILE = os.path.join(APP_DIR, "VERSION")
REQUIREMENTS = os.path.join(APP_DIR, "requirements.txt")

# 更新时跳过：运行环境、样例，以及用户自己的部署配置
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "samples", ".ota_backup", "node_modules"}
SKIP_FILES = {"docker-compose.yml", ".env", ".ota_state.json"}

API_COMMIT = "https://api.github.com/repos/%s/commits/%s" % (REPO, BRANCH)
RAW_VERSION = "https://raw.githubusercontent.com/%s/%s/VERSION" % (REPO, BRANCH)
TARBALL = "https://codeload.github.com/%s/tar.gz/refs/heads/%s" % (REPO, BRANCH)

_UA = {"User-Agent": "jw-shell-updater"}
_lock = threading.Lock()


def local_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or "unknown"
    except OSError:
        return "unknown"


def _remote_version():
    req = urllib.request.Request(RAW_VERSION + "?t=%d" % time.time(), headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", "replace").strip()


def _remote_commit():
    req = urllib.request.Request(
        API_COMMIT, headers=dict(_UA, **{"Accept": "application/vnd.github+json"})
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    commit = data.get("commit", {}) or {}
    message = commit.get("message") or ""
    return {
        "commit": (data.get("sha") or "")[:10],
        "message": message.splitlines()[0] if message else "",
        "date": (commit.get("committer") or {}).get("date", ""),
        "url": data.get("html_url", ""),
    }


def check():
    """返回本地/远端版本与是否有更新。"""
    result = {"enabled": ENABLED, "repo": REPO, "branch": BRANCH, "local": local_version()}
    if not ENABLED:
        return result
    try:
        result["remote"] = _remote_version()
        result["update_available"] = result["remote"] != result["local"]
    except Exception as exc:  # noqa: BLE001
        result["error"] = "无法获取远程版本：%s" % exc
        return result
    try:
        result.update(_remote_commit())
    except Exception:  # noqa: BLE001
        pass
    return result


def _backup():
    """备份当前代码，便于回滚。"""
    if os.path.isdir(BACKUP_DIR):
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for name in os.listdir(APP_DIR):
        if name in SKIP_DIRS or name in SKIP_FILES:
            continue
        src = os.path.join(APP_DIR, name)
        dst = os.path.join(BACKUP_DIR, name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_DIRS))
            else:
                shutil.copy2(src, dst)
        except OSError:
            pass


def _extract():
    """下载分支 tarball 并覆盖应用目录，返回覆盖文件数。"""
    req = urllib.request.Request(TARBALL + "?t=%d" % time.time(), headers=_UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        blob = resp.read()
    count = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = member.name.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            rel = parts[1]
            if rel.split("/")[0] in SKIP_DIRS or rel in SKIP_FILES:
                continue
            dest = os.path.join(APP_DIR, rel)
            if member.isdir():
                os.makedirs(dest, exist_ok=True)
            elif member.isfile():
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                src = tar.extractfile(member)
                if src is None:
                    continue
                with open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                count += 1
    return count


def _pip_install():
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", REQUIREMENTS],
            timeout=180, check=False,
        )
    except Exception:  # noqa: BLE001
        pass


def _restart():
    time.sleep(1.5)
    try:
        argv0 = os.path.basename(sys.argv[0] or "")
        if "gunicorn" in argv0:
            os.kill(os.getppid(), signal.SIGHUP)  # 让 gunicorn master 热重载 worker
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)  # 自重启
    except Exception:  # noqa: BLE001
        os._exit(0)


def _finish():
    time.sleep(1.0)
    _pip_install()
    _restart()


def apply():
    """执行更新：备份 -> 覆盖 -> 记录 -> 重装依赖 -> 重启。"""
    if not ENABLED:
        return {"ok": False, "error": "更新功能未启用（UPDATE_ENABLED=0）"}
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "已有更新正在进行"}
    try:
        try:
            info = _remote_commit()
        except Exception:  # noqa: BLE001
            info = {}
        _backup()
        count = _extract()
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"commit": info.get("commit"), "at": time.strftime("%Y-%m-%d %H:%M:%S")}, fh)
        threading.Thread(target=_finish, daemon=True).start()
        return {"ok": True, "files": count, "commit": info.get("commit"), "message": info.get("message", "")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    finally:
        _lock.release()
