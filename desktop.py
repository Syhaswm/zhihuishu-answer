"""桌面窗口。界面是 Vue 3 + Semi UI，答题逻辑仍调用 answer.py。"""

import base64
import ctypes
import functools
from contextlib import nullcontext
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
POLY_LOGIN_URL = "https://passport.zhihuishu.com/login?service=https%3A%2F%2Fhike-teaching-center.polymas.com%2F"
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


def _has_polymas(cookie_text):
    names = _cookie_names(cookie_text)
    return "polymas-token" in names and "AI-POLY-UINFO" in names


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
        pref = self._read_pref()
        provider = answer.find_provider(pref.get("provider"))
        saved_model = str(pref.get("model") or "")
        if provider["id"] == "deepseek" and saved_model in ("", "deepseek-chat"):
            saved_model = provider["model"]
        keys = pref.get("keys") if isinstance(pref.get("keys"), dict) else {}
        if api_key and not keys.get("deepseek"):
            keys["deepseek"] = api_key
        current_key = keys.get(provider["id"]) or ""
        if provider["id"] == "deepseek" and not current_key:
            current_key = api_key
        dock_side = str(pref.get("dockSide") or "off").lower()
        if dock_side not in ("off", "left", "right"):
            dock_side = "off"
        try:
            dock_width = int(pref.get("dockWidth") or 380)
        except (TypeError, ValueError):
            dock_width = 380
        dock_width = min(560, max(300, dock_width))
        dock_opacity = self._normalize_dock_opacity(pref.get("dockOpacity", 100))
        font_size = str(pref.get("answerFontSize") or "medium").lower()
        if font_size not in ("small", "medium", "large"):
            font_size = "medium"
        return {
            "apiKey": current_key,
            "keys": keys,
            "name": name,
            "expired": expired,
            "saveAnswers": self._save_answers(),
            "provider": provider["id"],
            "model": saved_model or provider["model"],
            "baseUrl": pref.get("baseUrl") or provider["url"],
            "thinking": bool(pref.get("thinking", False)),
            "dockSide": dock_side,
            "dockWidth": dock_width,
            "dockOnTop": bool(pref.get("dockOnTop", True)),
            "dockOpacity": dock_opacity,
            "answerShowReason": bool(pref.get("answerShowReason", False)),
            "answerFontSize": font_size,
            "providers": answer.PROVIDERS,
            "files": self._answer_files(),
        }

    def set_display_pref(self, show_reason=None, font_size=None):
        data = self._read_pref()
        if show_reason is not None:
            data["answerShowReason"] = bool(show_reason)
        if font_size is not None:
            size = str(font_size).lower()
            if size not in ("small", "medium", "large"):
                size = "medium"
            data["answerFontSize"] = size
        self._pref_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "answerShowReason": bool(data.get("answerShowReason", False)),
            "answerFontSize": str(data.get("answerFontSize") or "medium"),
        }

    @staticmethod
    def _normalize_dock_opacity(value):
        try:
            percent = int(value)
        except (TypeError, ValueError):
            percent = 100
        if percent >= 100:
            return 100
        if percent >= 95:
            return 95
        if percent >= 90:
            return 90
        return 85

    def set_dock_pref(self, side, width=380, always_on_top=True, opacity=None):
        side = str(side or "off").lower()
        if side not in ("off", "left", "right"):
            side = "off"
        try:
            width = int(width)
        except (TypeError, ValueError):
            width = 380
        width = min(560, max(300, width))
        data = self._read_pref()
        data["dockSide"] = side
        data["dockWidth"] = width
        data["dockOnTop"] = bool(always_on_top)
        if opacity is not None:
            data["dockOpacity"] = self._normalize_dock_opacity(opacity)
        self._pref_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "dockSide": side,
            "dockWidth": width,
            "dockOnTop": bool(always_on_top),
            "dockOpacity": self._normalize_dock_opacity(data.get("dockOpacity", 100)),
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

    def _read_pref(self):
        path = self._pref_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_answers(self):
        return bool(self._read_pref().get("saveAnswers", True))

    def _write_pref(self, enabled):
        data = self._read_pref()
        data["saveAnswers"] = bool(enabled)
        self._pref_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _save_model_pref(self, provider, model, base_url, api_key="", thinking=False):
        data = self._read_pref()
        data["provider"] = provider
        data["model"] = model
        data["baseUrl"] = base_url
        data["thinking"] = bool(thinking)
        keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
        keys[provider] = str(api_key or "")
        data["keys"] = keys
        self._pref_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

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
        allowed = (
            target.startswith("https://platform.deepseek.com"),
            target.startswith("https://gitee.com/Syhaswm/zhihuishu-answer/releases/"),
        )
        if not any(allowed):
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
        cookie = str(cookie_text or "")
        for url in (
            "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html",
            "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/currentTime",
        ):
            try:
                _resp, cookie = answer.request_with_sso(
                    "GET",
                    url,
                    cookie,
                    headers={"User-Agent": answer.HEADERS["User-Agent"], "Accept": "*/*"},
                    timeout=20,
                )
            except Exception:
                continue
        return cookie

    def _capture_polymas(self, cookie):
        """主站登录还留在这个窗口里时，顺手打开 AI 教学中心，把那边的登录一起保存。"""
        if _has_polymas(cookie) or not self._login_window_open():
            return cookie
        try:
            self._login.load_url(POLY_LOGIN_URL)
        except Exception:
            return cookie
        deadline = time.time() + 12
        while time.time() < deadline:
            if not self._login_window_open():
                break
            time.sleep(0.6)
            cookie = self._merge_cookie(cookie, self._cookies_from_login())
            if _has_polymas(cookie):
                break
        return cookie

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
        if not force and _has_polymas(cookie):
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
            if _has_polymas(cookie):
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
            cookie = self._capture_polymas(cookie)
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

    def clear_solve_checkpoint(self, text):
        urls = answer.split_homework_urls(text)
        if urls:
            answer.clear_checkpoint_urls(urls)
            return {"ok": True, "cleared": len(urls)}
        answer.save_checkpoint({"version": answer.CHECKPOINT_VERSION, "entries": {}})
        return {"ok": True, "cleared": "all"}
        answer.save_checkpoint({"version": answer.CHECKPOINT_VERSION, "entries": {}})
        return {"ok": True, "cleared": "all"}

    def solve_batch(self, text, api_key, provider="deepseek", model="", base_url="", thinking=False, resume=True):
        urls = answer.split_homework_urls(text)
        if not urls:
            return {"ok": False, "error": "请输入作业页地址，每行一个。", "papers": []}
        try:
            provider_info, endpoint, model_name = answer.resolve_provider(provider, model, base_url)
            if provider_info["needsKey"] and not str(api_key or "").strip():
                raise RuntimeError(f"请填写{provider_info['name']}的 API Key。")
            self._save_model_pref(provider_info["id"], model_name, endpoint, api_key, thinking)
            api_key, cookie = self._prepare_solve(api_key)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "papers": []}
        save_files = self._save_answers()
        folder = answer.ROOT / "答案" if save_files else None
        total = len(urls)
        if not resume:
            answer.clear_checkpoint_urls(urls)
        checkpoint = answer.load_checkpoint()
        skipped_chunks = 0
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
        found = {index: {} for index in range(total)}
        for index, exam in enumerate(fetched):
            if not exam:
                continue
            paper_url = urls[index]
            entry = (
                answer.checkpoint_entry(
                    checkpoint,
                    paper_url,
                    provider_info["id"],
                    model_name,
                    bool(thinking),
                    exam["questions"],
                )
                if resume
                else None
            )
            if entry:
                answer.merge_checkpoint_into_found(entry, found[index])
            for chunk in answer.question_chunks(exam["questions"]):
                if resume and entry and answer.checkpoint_chunk_answers(entry, chunk):
                    skipped_chunks += 1
                    continue
                jobs.append((index, chunk))
        chunk_errors = {}
        session_usage = answer.empty_usage()
        if skipped_chunks:
            self._progress(f"断点续答：跳过 {skipped_chunks} 组已答题目，待请求 {len(jobs)} 组…")
        if jobs:
            self._progress(f"正在同时解答 {len(jobs)} 组题目…")
            done = 0
            pin = answer.pinned_deepseek() if "api.deepseek.com" in endpoint else nullcontext()
            with pin:
                workers = min(answer.PARALLEL, len(jobs))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(
                            answer.ask_chunk,
                            api_key,
                            chunk,
                            endpoint,
                            model_name,
                            provider_info["name"],
                            provider_info["id"],
                            bool(thinking) and answer.supports_thinking(provider_info["id"], model_name),
                        ): (index, chunk)
                        for index, chunk in jobs
                    }
                    for future in as_completed(futures):
                        index, chunk = futures[future]
                        done += 1
                        try:
                            payload = future.result()
                            if isinstance(payload, dict):
                                batch = payload.get("answers") or []
                                answer.merge_usage(session_usage, payload.get("usage"))
                            else:
                                batch = payload or []
                            for item in batch:
                                found[index][item["n"]] = item
                            if resume:
                                exam = fetched[index]
                                if exam:
                                    answer.save_checkpoint_chunk(
                                        checkpoint,
                                        urls[index],
                                        provider_info["id"],
                                        model_name,
                                        bool(thinking),
                                        exam["questions"],
                                        chunk,
                                        payload if isinstance(payload, dict) else {"answers": batch},
                                    )
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
            complete = answer.paper_answers_complete(found[index], exam)
            result = answer.result_payload(exam, folder=folder, index=index + 1, save=save_files and complete)
            result["ok"] = complete
            result["url"] = url
            total_q = len(exam.get("questions") or [])
            answered_q = len(found[index])
            if not complete:
                missing = total_q - answered_q
                err = chunk_errors.get(index)
                hint = f"已答 {answered_q}/{total_q} 题"
                if missing:
                    hint += f"，还差 {missing} 题"
                hint += "。再次点「获取答案」且开启断点续答可只补未完成的题组。"
                result["error"] = str(err) if err else hint
                result["checkpointHint"] = hint
            elif resume:
                answer.clear_checkpoint_url(checkpoint, url)
            papers.append(result)
        done = sum(1 for paper in papers if paper.get("ok"))
        partial = sum(1 for paper in papers if not paper.get("ok") and paper.get("questions"))
        failed = total - done - partial
        if skipped_chunks:
            resume_note = f"断点续答跳过 {skipped_chunks} 组题目。"
        else:
            resume_note = ""
        if not done and not partial:
            summary = "这几份作业都没有取到答案。"
        elif partial and not done:
            summary = resume_note + f"有 {partial} 份只答了一部分，已写入断点，可再次获取续答。"
        elif not save_files:
            summary = resume_note + f"完成 {done} 份。" + (f"{failed} 份没有取到。" if failed else "")
            if partial:
                summary += f" {partial} 份未答全，可续答。"
            summary += "这次没有写入答案文件夹。"
        elif failed or partial:
            summary = resume_note + f"完成 {done} 份"
            if failed:
                summary += f"，{failed} 份没有取到"
            if partial:
                summary += f"，{partial} 份未答全（可续答）"
            summary += "。成功的答案保存在「答案」文件夹。"
        else:
            summary = resume_note + f"完成 {done} 份。每份答案单独保存在「答案」文件夹。"
        usage_text = answer.format_session_usage(session_usage)
        self._progress(summary if not usage_text else f"{summary}\n{usage_text}")
        return {
            "ok": done > 0 or partial > 0,
            "error": "" if (done or partial) else summary,
            "papers": papers,
            "summary": summary,
            "usage": session_usage,
            "usageText": usage_text,
            "skippedChunks": skipped_chunks,
            "resume": bool(resume),
        }


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
