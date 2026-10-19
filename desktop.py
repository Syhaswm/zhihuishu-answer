"""桌面窗口。界面是 Vue 3 + Semi UI，答题逻辑仍调用 answer.py。"""

import base64
import ctypes
import functools
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import unquote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import webview

import answer

LOGIN_URL = "https://passport.zhihuishu.com/login?service=https%3A%2F%2Fonlineweb.zhihuishu.com%2Fonlinestuh5"
def _resource_root():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return answer.ROOT


ICON = _resource_root() / "app.ico"
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


def _token_expired(cookie_text):
    for part in str(cookie_text or "").split(";"):
        part = part.strip()
        if not part.startswith("jt-cas="):
            continue
        payload = part.split("=", 1)[1].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        try:
            data = json.loads(base64.urlsafe_b64decode(payload))
        except Exception:
            return True
        return int(data.get("exp") or 0) <= int(time.time())
    return True


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
        cookie = self._saved_cookie()
        expired = _has_auth(cookie) and _token_expired(cookie)
        name = "" if expired else _account_name(cookie)
        return {"apiKey": api_key, "name": name, "expired": expired}

    def account(self):
        cookie = self._saved_cookie()
        expired = _has_auth(cookie) and _token_expired(cookie)
        name = "" if expired else _account_name(cookie)
        return {"loggedIn": bool(name), "name": name, "expired": expired}

    def open_url(self, url):
        target = str(url or "").strip()
        if not target.startswith("https://platform.deepseek.com"):
            return {"ok": False}
        webbrowser.open(target)
        return {"ok": True}

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
                if self._login.events.closed.is_set():
                    self._login = None
                else:
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
        if self._login.events.closed.is_set():
            self._login = None
            return None
        return self._login

    def _login_window_open(self):
        if self._login is None:
            return False
        try:
            return not self._login.events.closed.is_set()
        except Exception:
            return False

    def _login_cancelled(self, switch_account):
        if switch_account:
            return {"ok": False, "error": "登录窗口已关闭，当前账号没有更换。"}
        return {"ok": False, "error": "登录窗口已关闭。需要登录时再点「登录账号」。"}

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

    def _hide_login(self):
        if self._login is None:
            return
        try:
            if not self._login.events.closed.is_set():
                self._login.hide()
        except Exception:
            pass

    def _harvest_http(self, cookie_text):
        client = answer.session()
        client.headers.update(answer.HEADERS)
        client.cookies.update(answer.parse_cookie(cookie_text))
        for url in (
            "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html",
            "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/currentTime",
        ):
            try:
                client.get(url, timeout=20, allow_redirects=False)
            except Exception:
                continue
        picked = []
        for item in client.cookies:
            picked.append(f"{item.name}={item.value}")
        return "; ".join(picked)

    def _harvest(self, base=""):
        self._progress("正在补全登录信息…")
        self._hide_login()
        cookie = self._merge_cookie(base, self._cookies_from_login(), self._harvest_http(base))
        if _has_auth(cookie):
            self._save_cookie(cookie)
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

    def _sync_polymas(self, url, cookie, force=False):
        if not force and "polymas-token=" in cookie and "AI-POLY-UINFO=" in cookie:
            return cookie
        self._progress("正在打开这份作业页，同步 AI 教学中心登录…")
        self._ensure_login_window()
        self._login.load_url(url)
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1.2)
            cookie = self._merge_cookie(cookie, self._cookies_from_login())
            if "polymas-token=" in cookie and "AI-POLY-UINFO=" in cookie:
                self._save_cookie(cookie)
                return cookie
        self._save_cookie(cookie)
        try:
            self._login.show()
        except Exception:
            pass
        return cookie

    def begin_login(self, switch_account=False):
        self._progress("请在弹出的窗口登录智慧树，登录成功后会自动保存")
        try:
            if self._ensure_login_window() is None:
                return self._login_cancelled(switch_account)
            if switch_account:
                try:
                    self._login.clear_cookies()
                except Exception:
                    pass
            self._login.load_url(LOGIN_URL)
        except Exception as exc:
            if not self._login_window_open():
                return self._login_cancelled(switch_account)
            return {"ok": False, "error": "登录窗口没有打开：" + str(exc)}
        apply_icon()
        deadline = time.time() + 180
        while time.time() < deadline:
            for _ in range(4):
                if not self._login_window_open():
                    return self._login_cancelled(switch_account)
                time.sleep(0.3)
            if not self._login_window_open():
                return self._login_cancelled(switch_account)
            cookie = self._cookies_from_login()
            if not _has_auth(cookie):
                continue
            self._hide_login()
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
        if _token_expired(cookie):
            return {"ok": False, "error": "登录已过期。请点「切换账号」，在弹出的窗口重新登录后再获取答案。"}
        try:
            if answer.is_polymas_url(url):
                cookie = self._sync_polymas(url, cookie)
            result = answer.run(url, cookie=cookie, api_key=api_key, on_progress=self._progress)
        except RuntimeError as exc:
            text = str(exc)
            if "参数" not in text and "不属于" not in text and "登录" not in text and "失效" not in text:
                return {"ok": False, "error": text}
            if answer.is_polymas_url(url):
                cookie = self._sync_polymas(url, cookie, force=True)
            else:
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
    dist = _resource_root() / "ui" / "dist"
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
