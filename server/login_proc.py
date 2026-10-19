"""登录窗口进程。读到智慧树 Cookie 后写入 login_result.json 并退出。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import answer
import desktop
import webview


def main():
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
