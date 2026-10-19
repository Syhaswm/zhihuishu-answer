"""登录窗口进程。读到智慧树 Cookie 后写入结果文件并退出。"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import answer
import desktop
import webview


def sync_polymas():
    request_path = answer.ROOT / "sync_request.json"
    result_path = answer.ROOT / "sync_result.json"
    url = json.loads(request_path.read_text(encoding="utf-8"))["url"]
    api = desktop.Api()
    window = webview.create_window(
        "同步登录",
        url,
        width=1100,
        height=760,
        hidden=True,
        text_select=True,
    )
    api._login = window

    def run():
        cookie = api._saved_cookie()
        deadline = time.time() + 12
        revealed = False
        ok = False
        while time.time() < deadline:
            if not api._login_window_open():
                break
            cookie = api._merge_cookie(cookie, api._cookies_from_login())
            if desktop._has_polymas(cookie):
                api._save_cookie(cookie)
                ok = True
                break
            if not revealed and time.time() > deadline - 1:
                try:
                    window.show()
                except Exception:
                    pass
                revealed = True
                deadline = time.time() + 40
            time.sleep(0.8)
        if ok:
            result = {"ok": True}
        elif revealed:
            result = {"ok": False, "error": "没有读到 AI 教学中心的登录。请在弹出的窗口登录后再点获取答案。"}
        else:
            result = {"ok": False, "error": "没能在后台同步登录。请点「切换账号」重新登录后再获取答案。"}
        result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        try:
            if api._login_window_open():
                window.destroy()
        except Exception:
            pass

    profile = answer.ROOT / "profile"
    profile.mkdir(exist_ok=True)
    webview.start(
        run,
        private_mode=False,
        storage_path=str(profile),
        user_agent=answer.HEADERS["User-Agent"],
    )


def main():
    if "--sync" in sys.argv:
        sync_polymas()
        return
    switch = "--switch" in sys.argv
    api = desktop.Api()
    result_path = answer.ROOT / "login_result.json"
    window = webview.create_window(
        "登录智慧树",
        desktop.LOGIN_URL,
        width=1100,
        height=760,
        text_select=True,
    )
    api._login = window

    def run():
        try:
            result = api.begin_login(switch)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        try:
            if api._login is not None and not api._login.events.closed.is_set():
                api._login.destroy()
        except Exception:
            pass

    profile = answer.ROOT / "profile"
    profile.mkdir(exist_ok=True)
    webview.start(
        run,
        private_mode=False,
        storage_path=str(profile),
        user_agent=answer.HEADERS["User-Agent"],
    )


if __name__ == "__main__":
    main()
