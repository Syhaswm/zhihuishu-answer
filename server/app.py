"""本机 FastAPI。只监听 127.0.0.1，并且每次启动都要核对随机口令。"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import answer
import desktop
import usage_query

app = FastAPI(title="智慧树答题", docs_url=None, redoc_url=None, openapi_url=None)

API_TOKEN = os.environ.get("ZHS_API_TOKEN", "")
SIGN_WINDOW_MS = 120_000


def _sign(timestamp, method, path, body):
    payload = f"{timestamp}\n{method}\n{path}\n{body}".encode()
    return hmac.new(API_TOKEN.encode(), payload, hashlib.sha256).hexdigest()


@app.middleware("http")
async def allow_private_network(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.middleware("http")
async def require_sign(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if not API_TOKEN:
        return JSONResponse({"error": "无权访问"}, status_code=401)
    timestamp = request.headers.get("x-zhs-timestamp") or ""
    sign = request.headers.get("x-zhs-sign") or ""
    try:
        stamp = int(timestamp)
    except ValueError:
        return JSONResponse({"error": "无权访问"}, status_code=401)
    if abs(int(time.time() * 1000) - stamp) > SIGN_WINDOW_MS:
        return JSONResponse({"error": "请求已过期"}, status_code=401)
    body = (await request.body()).decode("utf-8")
    expected = _sign(timestamp, request.method.upper(), request.url.path, body)
    if not hmac.compare_digest(expected, sign):
        return JSONResponse({"error": "无权访问"}, status_code=401)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "x-zhs-timestamp", "x-zhs-sign"],
    allow_private_network=True,
)

api = desktop.Api()
_login_proc = None
_login_lock = threading.Lock()


class SaveIn(BaseModel):
    enabled: bool


class DockIn(BaseModel):
    side: str = "off"
    width: int = 380
    alwaysOnTop: bool = True


class DisplayIn(BaseModel):
    showReason: bool | None = None
    fontSize: str | None = None


class NamesIn(BaseModel):
    names: list[str] = []


class OpenIn(BaseModel):
    url: str


class SolveIn(BaseModel):
    urls: str = ""
    apiKey: str = ""
    provider: str = "deepseek"
    model: str = ""
    baseUrl: str = ""
    thinking: bool = False


class LoginIn(BaseModel):
    switch: bool = False


class UpdateIn(BaseModel):
    current: str = ""


class ModelsIn(BaseModel):
    provider: str = "deepseek"
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""


def _version_key(text):
    numbers = []
    for part in str(text or "").replace("v", " ").replace("V", " ").replace(".", " ").split():
        if part.isdigit():
            numbers.append(int(part))
    return tuple(numbers[:3])


def _pythonw():
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate if candidate.exists() else sys.executable)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/settings")
def settings():
    return api.load_settings()


@app.post("/api/settings/save")
def set_save(body: SaveIn):
    return api.set_save_answers(body.enabled)


@app.post("/api/settings/dock")
def set_dock(body: DockIn):
    return api.set_dock_pref(body.side, body.width, body.alwaysOnTop)


@app.post("/api/settings/display")
def set_display(body: DisplayIn):
    return api.set_display_pref(body.showReason, body.fontSize)


@app.get("/api/answers")
def list_answers():
    return api.list_answers()


@app.post("/api/answers/delete")
def delete_answers(body: NamesIn):
    return api.delete_answers(body.names)


@app.post("/api/answers/delete-all")
def delete_all_answers():
    return api.delete_all_answers()


@app.post("/api/open-url")
def open_url(body: OpenIn):
    return api.open_url(body.url)


@app.post("/api/models")
def model_list(body: ModelsIn):
    try:
        names = answer.list_models(body.provider, body.baseUrl, body.apiKey)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "models": []}
    return {"ok": True, "models": names}


@app.post("/api/models/test")
def test_model(body: ModelsIn):
    try:
        result = answer.probe_connection(body.provider, body.model, body.baseUrl, body.apiKey)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **result}


@app.post("/api/usage")
def model_usage(body: ModelsIn):
    try:
        result = usage_query.query_usage(body.provider, body.baseUrl, body.apiKey)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **result}


@app.post("/api/update")
def check_update(body: UpdateIn):
    current = str(body.current or "").strip()

    def failed(message):
        return {
            "update": False,
            "current": current,
            "checkOk": False,
            "checkMessage": message,
        }

    try:
        response = answer.session().get(
            "https://gitee.com/api/v5/repos/Syhaswm/zhihuishu-answer/releases",
            params={"page": 1, "per_page": 20, "direction": "desc"},
            timeout=8,
        )
    except Exception:
        return failed("暂时无法连接更新服务器，请检查网络。可稍后点「重试」，或到 Gitee 发行版页手动查看。")
    try:
        releases = response.json()
    except ValueError:
        return failed("更新服务器返回异常，请稍后再试。")
    if not response.ok:
        return failed(f"检查更新失败（HTTP {response.status_code}），请稍后再试。")
    if not isinstance(releases, list) or not releases:
        return failed("没有读取到发行版信息，请稍后再试。")
    payload = max(releases, key=lambda item: _version_key(item.get("tag_name")))
    latest = str(payload.get("tag_name") or "").lstrip("vV")
    if not latest or _version_key(latest) <= _version_key(current):
        return {"update": False, "current": current, "latest": latest, "checkOk": True}
    download = ""
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        if name.endswith("Setup.exe"):
            download = str(asset.get("browser_download_url") or "")
            break
    if not download:
        download = f"https://gitee.com/Syhaswm/zhihuishu-answer/releases/tag/v{latest}"
    return {
        "update": True,
        "current": current,
        "latest": latest,
        "url": download,
        "checkOk": True,
    }


@app.post("/api/login")
def begin_login(body: LoginIn):
    global _login_proc
    result_path = answer.ROOT / "login_result.json"
    if result_path.exists():
        result_path.unlink()
    with _login_lock:
        if _login_proc is not None and _login_proc.poll() is None:
            return {"ok": True, "pending": True}
        script = Path(__file__).resolve().parent / "login_proc.py"
        args = [_pythonw(), str(script)]
        if body.switch:
            args.append("--switch")
        _login_proc = subprocess.Popen(args, cwd=str(ROOT))
    return {"ok": True, "pending": True}


@app.get("/api/login/status")
def login_status():
    result_path = answer.ROOT / "login_result.json"
    if result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"ok": False, "error": "登录结果读不出来，请再点一次登录。"}
    proc = _login_proc
    if proc is not None and proc.poll() is not None:
        return {"ok": False, "error": "登录窗口已关闭。需要登录时再点「登录账号」。"}
    return {"ok": False, "pending": True}


@app.post("/api/solve")
def solve(body: SolveIn):
    events = Queue()

    def on_progress(message):
        events.put({"type": "progress", "message": message})

    def work():
        api._on_progress = on_progress
        try:
            result = api.solve_batch(
                body.urls, body.apiKey, body.provider, body.model, body.baseUrl, body.thinking
            )
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "papers": [], "summary": str(exc)}
        finally:
            api._on_progress = None
        result["type"] = "result"
        events.put(result)
        events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            try:
                item = events.get(timeout=180)
            except Empty:
                yield json.dumps({"type": "result", "ok": False, "error": "获取答案超时。", "papers": []}, ensure_ascii=False) + "\n"
                break
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
