"""桌面窗口。界面是 Vue 3 + Semi UI，答题逻辑仍调用 answer.py。"""

import ctypes
import functools
import json
import threading
import time
from urllib.parse import unquote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import webview

import answer

LOGIN_URL = "https://passport.zhihuishu.com/login?service=https%3A%2F%2Fonlineweb.zhihuishu.com%2Fonlinestuh5"
ICON = answer.ROOT / "app.ico"
_ICON_HANDLE = None


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def _cookie_names(cookie_text):
    names = set()
    for part in str(cookie_text or "").split(";"):
        if "=" in part:
            names.add(part.split("=", 1)[0].strip())
    return names


def _has_auth(cookie_text):
    return {"CASTGC", "jt-cas", "CASLOGC"}.issubset(_cookie_names(cookie_text))


def _account_name(cookie_text):
    for part in str(cookie_text or "").split(";"):
        part = part.strip()
        if not part.startswith("CASLOGC="):
            continue
        raw = unquote(part.split("=", 1)[1])
        try:
            return json.loads(raw).get("realName") or ""
        except json.JSONDecodeError:
            return ""
    return ""


def _format_cookies(cookies):
    pairs = []
    seen = set()
    for cookie in cookies or []:
        for name in cookie.keys():
            if name in seen:
                continue
            seen.add(name)
            pairs.append(f"{name}={cookie[name].value}")
    return "; ".join(pairs)


def apply_icon():
    global _ICON_HANDLE
    if not ICON.exists():
        return
    user32 = ctypes.windll.user32
    if not _ICON_HANDLE:
        _ICON_HANDLE = user32.LoadImageW(None, str(ICON), 1, 0, 0, 0x10)
    if not _ICON_HANDLE:
        return
    for title in ("智慧树答题", "登录智慧树"):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            user32.PostMessageW(hwnd, 0x80, 1, _ICON_HANDLE)
            user32.PostMessageW(hwnd, 0x80, 0, _ICON_HANDLE)


class Api:
    def __init__(self):
        self._main = None
        self._login = None

    def load_settings(self):
        try:
            api_key = answer.load_api_key()
        except RuntimeError:
            api_key = ""
        name = _account_name(self._saved_cookie())
        return {"apiKey": api_key, "name": name}

    def account(self):
        name = _account_name(self._saved_cookie())
        return {"loggedIn": bool(name) or _has_auth(self._saved_cookie()), "name": name}

    def _progress(self, message):
        script = "window.onSolveProgress && window.onSolveProgress(%s)" % json.dumps(
            message, ensure_ascii=False
        )
        try:
            self._main.evaluate_js(script)
        except Exception:
            pass

    def _saved_cookie(self):
        path = answer.ROOT / "cookie.txt"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _save_cookie(self, cookie):
        if cookie:
            (answer.ROOT / "cookie.txt").write_text(cookie, encoding="utf-8")

    def _ensure_login_window(self):
        if self._login is not None:
            try:
                self._login.show()
                return self._login
            except Exception:
                self._login = None
        self._login = webview.create_window(
            "登录智慧树",
            LOGIN_URL,
            width=1100,
            height=760,
            text_select=True,
        )
        self._login.events.loaded.wait(25)
        return self._login

    def _cookies_from_login(self):
        if self._login is None:
            return ""
        try:
            return _format_cookies(self._login.get_cookies())
        except Exception:
            return ""

    def _merge_cookie(self, *texts):
        jar = {}
        for text in texts:
            for part in str(text or "").split(";"):
                part = part.strip()
                if "=" not in part:
                    continue
                key, value = part.split("=", 1)
                jar[key.strip()] = value.strip()
        return "; ".join(f"{key}={value}" for key, value in jar.items())

    def _read_site(self, url):
        self._login.load_url(url)
        time.sleep(3)
        return self._cookies_from_login()

    def _harvest(self, base=""):
        self._progress("正在补全登录信息…")
        self._ensure_login_window()
        parts = [base, self._cookies_from_login()]
        for url in (
            "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html",
            "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/currentTime",
        ):
            try:
                parts.append(self._read_site(url))
            except Exception:
                continue
        cookie = self._merge_cookie(*parts)
        if _has_auth(cookie):
            self._save_cookie(cookie)
        try:
            self._login.hide()
        except Exception:
            pass
        return cookie

    def _clear_saved_login(self):
        cookie_path = answer.ROOT / "cookie.txt"
        if cookie_path.exists():
            cookie_path.unlink()
        if self._login is not None:
            try:
                self._login.clear_cookies()
            except Exception:
                pass

    def begin_login(self, switch_account=False):
        if switch_account:
            self._clear_saved_login()
        self._progress("请在弹出的窗口登录智慧树，登录成功后会自动保存")
        try:
            self._ensure_login_window()
            self._login.load_url(LOGIN_URL)
        except Exception as exc:
            return {"ok": False, "error": "登录窗口没有打开：" + str(exc)}
        apply_icon()
        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(1.2)
            cookie = self._cookies_from_login()
            if not _has_auth(cookie):
                continue
            cookie = self._harvest(cookie)
            name = _account_name(cookie) or "已登录"
            self._progress("已保存登录：" + name)
            return {"ok": True, "name": name}
        return {"ok": False, "error": "还没有读到登录信息。请在弹出的窗口完成登录后再点一次登录账号。"}

    def solve(self, url, api_key):
        api_key = str(api_key or "").strip()
        if api_key:
            (answer.ROOT / "apikey.txt").write_text(api_key + "\n", encoding="utf-8")
        cookie = self._saved_cookie()
        if not _has_auth(cookie):
            return {"ok": False, "error": "请先点「登录账号」，在弹出的窗口登录。登录只会在你点这个按钮时进行。"}
        try:
            result = answer.run(url, cookie=cookie, api_key=api_key, on_progress=self._progress)
        except RuntimeError as exc:
            text = str(exc)
            if "参数" not in text and "不属于" not in text and "登录" not in text and "失效" not in text:
                return {"ok": False, "error": text}
            cookie = self._harvest(cookie)
            if not _has_auth(cookie):
                return {"ok": False, "error": "登录信息不完整。请点「切换账号」重新登录。"}
            try:
                result = answer.run(url, cookie=cookie, api_key=api_key, on_progress=self._progress)
            except Exception as exc2:
                return {"ok": False, "error": str(exc2)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        result["ok"] = True
        return result


def _serve(directory):
    handler = functools.partial(_QuietHandler, directory=str(directory))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Zhihuishu.Answer")
    dist = answer.ROOT / "ui" / "dist"
    index = dist / "index.html"
    if not index.exists():
        raise SystemExit("界面文件缺失。请先在 ui 目录执行 npm install 和 npm run build。")
    httpd = _serve(dist)
    port = httpd.server_address[1]
    api = Api()
    main_window = webview.create_window(
        "智慧树答题",
        f"http://127.0.0.1:{port}/index.html",
        js_api=api,
        width=1080,
        height=800,
        min_size=(880, 640),
        background_color="#F4F5F7",
        text_select=True,
    )
    api._main = main_window
    main_window.events.shown += apply_icon
    profile = answer.ROOT / "profile"
    profile.mkdir(exist_ok=True)
    webview.start(
        private_mode=False,
        storage_path=str(profile),
        user_agent=answer.HEADERS["User-Agent"],
    )
    httpd.shutdown()


if __name__ == "__main__":
    main()
