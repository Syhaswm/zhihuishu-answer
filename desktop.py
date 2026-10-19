"""桌面窗口。界面是 Vue 3 + Semi UI，答题逻辑仍调用 answer.py。"""

import base64
import ctypes
import functools
import json
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        self._batch_label = ""
        self._progress_lock = threading.Lock()
        self._on_progress = None

    def load_settings(self):
        try:
            api_key = answer.load_api_key()
        except RuntimeError:
            api_key = ""
        cookie = self._saved_cookie()
        expired = _has_auth(cookie) and _token_expired(cookie)
        name = "" if expired else _account_name(cookie)
        return {
            "apiKey": api_key,
            "name": name,
            "expired": expired,
            "saveAnswers": self._save_answers(),
            "files": self._answer_files(),
        }

    def set_save_answers(self, enabled):
        self._write_pref(bool(enabled))
        return {"ok": True, "saveAnswers": self._save_answers(), "files": self._answer_files()}

    def list_answers(self):
        return {"files": self._answer_files()}

    def delete_answers(self, names):
        if isinstance(names, str):
            names = [names]
        folder = self._answer_dir().resolve()
        removed = []
        for name in names or []:
            path = self._answer_file(name, folder)
            if path is None:
                continue
            path.unlink()
            removed.append(path.name)
        return {"ok": True, "removed": removed, "files": self._answer_files()}

    def delete_all_answers(self):
        folder = self._answer_dir()
        if folder.exists():
            shutil.rmtree(folder)
        return {"ok": True, "files": []}

    def _pref_path(self):
        return answer.ROOT / "settings.json"

    def _save_answers(self):
        path = self._pref_path()
        if not path.exists():
            return True
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        return bool(data.get("saveAnswers", True))

    def _write_pref(self, enabled):
        self._pref_path().write_text(
            json.dumps({"saveAnswers": bool(enabled)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _answer_dir(self):
        return answer.ROOT / "答案"

    def _answer_file(self, name, folder):
        text = str(name or "").strip()
        if not text or text != Path(text).name or not text.lower().endswith(".txt"):
            return None
        path = (folder / text).resolve()
        if path.parent != folder or not path.is_file():
            return None
        return path

    def _answer_files(self):
        folder = self._answer_dir()
        if not folder.is_dir():
            return []
        files = []
        for path in sorted(folder.glob("*.txt")):
            if path.is_file():
                files.append({"name": path.name, "size": path.stat().st_size})
        return files

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
        if self._batch_label:
            message = self._batch_label + message
        if self._on_progress:
            try:
                self._on_progress(message)
            except Exception:
                pass
            return
        script = "window.onSolveProgress && window.onSolveProgress(%s)" % json.dumps(
            message, ensure_ascii=False
        )
        with self._progress_lock:
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
        if webview.guilib is None:
            return self._sync_polymas_process(url)
        try:
            self._ensure_login_window()
            self._login.load_url(url)
        except Exception as exc:
            raise RuntimeError("登录窗口没有打开。请点「切换账号」重新登录后再获取答案。") from exc
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1.2)
            cookie = self._merge_cookie(cookie, self._cookies_from_login())
            if "polymas-token=" in cookie and "AI-POLY-UINFO=" in cookie:
                self._save_cookie(cookie)
                self._hide_login()
                return cookie
        self._hide_login()
        raise RuntimeError("没有读到 AI 教学中心的登录。请点「切换账号」重新登录后再获取答案。")

    def _sync_polymas_process(self, url):
        request_path = answer.ROOT / "sync_request.json"
        result_path = answer.ROOT / "sync_result.json"
        if result_path.exists():
            result_path.unlink()
        request_path.write_text(json.dumps({"url": url}, ensure_ascii=False), encoding="utf-8")
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = str(pythonw if pythonw.exists() else sys.executable)
        script = answer.ROOT / "server" / "login_proc.py"
        proc = subprocess.Popen([exe, str(script), "--sync"], cwd=str(answer.ROOT))
        deadline = time.time() + 50
        while time.time() < deadline:
            if result_path.exists() or proc.poll() is not None:
                break
            time.sleep(0.4)
        else:
            proc.kill()
            raise RuntimeError("同步 AI 教学中心登录超时。请点「切换账号」重新登录后再获取答案。")
        if not result_path.exists():
            raise RuntimeError("没能打开作业页同步登录。请点「切换账号」重新登录后再获取答案。")
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("同步登录的结果读不出来。请再点一次获取答案。") from exc
        if not data.get("ok"):
            raise RuntimeError(data.get("error") or "没有读到 AI 教学中心的登录。请点「切换账号」重新登录后再获取答案。")
        return self._saved_cookie()

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

    def _prepare_solve(self, api_key):
        api_key = str(api_key or "").strip()
        if api_key:
            (answer.ROOT / "apikey.txt").write_text(api_key + "\n", encoding="utf-8")
        cookie = self._saved_cookie()
        if not _has_auth(cookie):
            raise RuntimeError("请先点「登录账号」，在弹出的窗口登录。登录只会在你点这个按钮时进行。")
        if _token_expired(cookie):
            raise RuntimeError("登录已过期。请点「切换账号」，在弹出的窗口重新登录后再获取答案。")
        return api_key, cookie

    def _solve_one(self, url, api_key, cookie, folder, index):
        def once(current):
            if answer.is_polymas_url(url):
                current = self._sync_polymas(url, current)
            result = answer.run(
                url,
                cookie=current,
                api_key=api_key,
                on_progress=self._progress,
                folder=folder,
                index=index,
            )
            return result, current

        try:
            result, cookie = once(cookie)
        except RuntimeError as exc:
            text = str(exc)
            if "参数" not in text and "不属于" not in text and "登录" not in text and "失效" not in text:
                raise
            if answer.is_polymas_url(url):
                cookie = self._sync_polymas(url, cookie, force=True)
            else:
                cookie = self._harvest(cookie)
            if not _has_auth(cookie):
                raise RuntimeError("登录信息不完整。请点「切换账号」重新登录。") from exc
            result, cookie = once(cookie)
        result["ok"] = True
        result["url"] = url
        return result, cookie

    def solve(self, url, api_key):
        try:
            api_key, cookie = self._prepare_solve(api_key)
            result, _cookie = self._solve_one(url, api_key, cookie, None, 1)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return result

    def _failed_paper(self, index, url, exc):
        return {
            "ok": False,
            "url": url,
            "title": f"第 {index + 1} 份没有取到",
            "course": "",
            "error": str(exc or "没有返回题目"),
            "questions": [],
            "text": "",
            "file": "",
            "path": "",
        }

    def _should_retry(self, exc):
        text = str(exc or "")
        return any(word in text for word in ("参数", "不属于", "登录", "失效"))

    def _fetch_all(self, urls, cookie):
        if not urls:
            return [], []
        fetched = [None] * len(urls)
        errors = [None] * len(urls)
        workers = min(answer.PARALLEL, len(urls))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(answer.fetch_homework, url, cookie): index
                for index, url in enumerate(urls)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    fetched[index] = future.result()
                except Exception as exc:
                    errors[index] = exc
        return fetched, errors

    def solve_batch(self, text, api_key):
        urls = answer.split_homework_urls(text)
        if not urls:
            return {"ok": False, "error": "请输入作业页地址，每行一个。", "papers": []}
        try:
            api_key, cookie = self._prepare_solve(api_key)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "papers": []}
        save_files = self._save_answers()
        folder = answer.ROOT / "答案" if save_files else None
        total = len(urls)
        for url in urls:
            if answer.is_polymas_url(url):
                cookie = self._sync_polymas(url, cookie)
        self._progress(f"正在同时拉取 {total} 份题目…")
        fetched, errors = self._fetch_all(urls, cookie)
        if any(self._should_retry(errors[i]) for i in range(total)):
            cookie = self._harvest(cookie)
            retry_urls = [(i, urls[i]) for i in range(total) if self._should_retry(errors[i])]
            refetched, reerrors = self._fetch_all([url for _i, url in retry_urls], cookie)
            for (i, _url), exam, exc in zip(retry_urls, refetched, reerrors):
                fetched[i] = exam
                errors[i] = exc
        jobs = []
        for index, exam in enumerate(fetched):
            if not exam:
                continue
            for chunk in answer.question_chunks(exam["questions"]):
                jobs.append((index, chunk))
        found = {index: {} for index in range(total)}
        chunk_errors = {}
        if jobs:
            self._progress(f"正在同时解答 {len(jobs)} 组题目…")
            done = 0
            with answer.pinned_deepseek():
                workers = min(answer.PARALLEL, len(jobs))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(answer.ask_chunk, api_key, chunk): (index, chunk)
                        for index, chunk in jobs
                    }
                    for future in as_completed(futures):
                        index, chunk = futures[future]
                        done += 1
                        try:
                            for item in future.result():
                                found[index][item["n"]] = item
                        except Exception as exc:
                            chunk_errors.setdefault(index, exc)
                        self._progress(f"解答进度 {done}/{len(jobs)}")
        papers = []
        for index, url in enumerate(urls):
            exam = fetched[index]
            if errors[index] or exam is None:
                papers.append(self._failed_paper(index, url, errors[index]))
                continue
            if index in chunk_errors and not found[index]:
                papers.append(self._failed_paper(index, url, chunk_errors[index]))
                continue
            answer.apply_answers(exam, found[index])
            result = answer.result_payload(exam, folder=folder, index=index + 1, save=save_files)
            result["ok"] = True
            result["url"] = url
            papers.append(result)
        done = sum(1 for paper in papers if paper.get("ok"))
        failed = total - done
        if not done:
            summary = "这几份作业都没有取到答案。"
        elif not save_files:
            summary = f"完成 {done} 份。" + (f"{failed} 份没有取到。" if failed else "") + "这次没有写入答案文件夹。"
        elif failed:
            summary = f"完成 {done} 份，{failed} 份没有取到。成功的答案分别保存在「答案」文件夹。"
        else:
            summary = f"完成 {done} 份。每份答案单独保存在「答案」文件夹。"
        self._progress(summary)
        return {"ok": done > 0, "error": "" if done else summary, "papers": papers, "summary": summary}


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
