"""输入智慧树作业页地址，拉取题目后用 DeepSeek 返回答案。

不会交卷。Cookie 过期后，在已登录的浏览器里打开作业页，
从 F12 复制整段 Cookie，替换下面的 COOKIE。
通常要更新的是 CASTGC、jt-cas、CASLOGC、JSESSIONID、acw_tc、SERVERID。
"""

import json
import re
import socket
import sys
import threading
import time
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from Crypto.Cipher import AES

# 命令行使用时，把浏览器里复制的 Cookie 整段贴到这里。桌面程序请点「登录账号」，不要把登录凭证提交到仓库。
COOKIE = ""

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://onlineexamh5new.zhihuishu.com",
    "Referer": "https://onlineexamh5new.zhihuishu.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

HOMEWORK_URL = "https://studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/doHomework"
AES_KEY = b"onbfhdyvz8x7otrp"
AES_IV = b"1g3qqdh4jvbskb9x"
API_BASE = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek", "url": API_BASE, "model": MODEL, "needsKey": True, "hint": "在 DeepSeek 开放平台创建的 Key"},
    {"id": "qwen", "name": "通义千问", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "model": "qwen-plus", "needsKey": True, "hint": "阿里云百炼的 API Key"},
    {"id": "zhipu", "name": "智谱 GLM", "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "model": "glm-4-flash", "needsKey": True, "hint": "智谱开放平台的 API Key"},
    {"id": "kimi", "name": "Kimi", "url": "https://api.moonshot.cn/v1/chat/completions", "model": "moonshot-v1-8k", "needsKey": True, "hint": "Moonshot 开放平台的 API Key"},
    {"id": "doubao", "name": "豆包", "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "model": "", "needsKey": True, "hint": "火山方舟的 API Key，模型填接入点 ID"},
    {"id": "openai", "name": "OpenAI", "url": "https://api.openai.com/v1/chat/completions", "model": "gpt-4o-mini", "needsKey": True, "hint": "OpenAI 的 API Key"},
    {"id": "gemini", "name": "Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "model": "gemini-2.0-flash", "needsKey": True, "hint": "Google AI Studio 的 API Key"},
    {"id": "ollama", "name": "本地 Ollama", "url": "http://127.0.0.1:11434/v1/chat/completions", "model": "qwen2.5:7b", "needsKey": False, "hint": "先在本机启动 Ollama，模型名与本地一致"},
    {"id": "lmstudio", "name": "本地 LM Studio", "url": "http://127.0.0.1:1234/v1/chat/completions", "model": "", "needsKey": False, "hint": "先在 LM Studio 里加载模型并打开本地服务"},
    {"id": "custom", "name": "自定义接口", "url": "", "model": "", "needsKey": False, "hint": "填写兼容 OpenAI 的接口地址和模型名"},
]
PARALLEL = 6
CHUNK = 4
_PINNED_IP = None
_PINNED_LOCK = threading.Lock()
def _runtime_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = _runtime_root()


def parse_cookie(raw):
    jar = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        jar[key.strip()] = value.strip()
    return jar


def session():
    client = requests.Session()
    client.trust_env = False
    client.proxies = {"http": None, "https": None}
    return client


def _port_open(host, port, timeout=2):
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def deepseek_addresses():
    try:
        infos = socket.getaddrinfo("api.deepseek.com", 443, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        return [None]
    ips = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    reachable = [ip for ip in ips if _port_open(ip, 443)]
    return reachable or ips or [None]


def encrypt_params(payload):
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    pad = 16 - len(raw) % 16
    raw += bytes([pad]) * pad
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return b64encode(cipher.encrypt(raw)).decode()


def parse_homework_url(url):
    text = unquote(url.strip())
    hashed = text.split("#", 1)[1] if "#" in text else text
    hashed = hashed.split("?", 1)[0]
    parts = [item for item in hashed.split("/") if item]
    if "dohomework" not in parts:
        raise ValueError(
            "这不是作业做题页地址。请粘贴浏览器里打开作业后的完整地址。"
            "普通作业页路径里有 /webExamList/dohomework/，"
            "AI 教学中心作业页路径里有 /exam-hub/ 和 answer-homework。"
        )
    index = parts.index("dohomework")
    fields = parts[index + 1 :]
    if len(fields) < 5:
        raise ValueError("地址里的作业参数不完整，请从浏览器地址栏整段复制。")
    return {
        "recruitId": fields[0],
        "examId": fields[2],
        "studentExamId": fields[1],
        "schoolId": fields[4],
        "courseId": fields[3],
    }


POLY_ORIGIN = "https://hike-teaching-center.polymas.com"
POLY_EXAM_API = "https://cloudapi.polymas.com/student-homework/homeworkStudentExam/queryExamInfo"
POLY_DETAIL_API = "https://cloudapi.polymas.com/student-homework/homeworkStudent/getStudentHomeworkDetail"


def is_polymas_url(url):
    text = unquote(str(url or "")).strip().lower()
    return "polymas.com" in text and "answer-homework" in text


def parse_polymas_url(url):
    text = unquote(url.strip())
    parsed = urlparse(text)
    parts = [item for item in parsed.path.split("/") if item]
    query = parse_qs(parsed.query)
    if parsed.fragment and "homeworkId" not in parsed.query:
        fragment = parsed.fragment
        if "?" in fragment:
            fragment_path, fragment_query = fragment.split("?", 1)
            query = parse_qs(fragment_query)
            parts = [item for item in fragment_path.split("/") if item]
    if "exam-hub" not in parts:
        raise ValueError("这不是 AI 教学中心的作业做题页。请从浏览器地址栏整段复制。")
    course_id = parts[parts.index("exam-hub") + 1] if len(parts) > parts.index("exam-hub") + 1 else ""
    homework_id = (query.get("homeworkId") or [""])[0]
    paper_id = (query.get("paperId") or [""])[0]
    exam_id = (query.get("examId") or [""])[0]
    if not all([course_id, homework_id, paper_id, exam_id]):
        raise ValueError("地址里的作业参数不完整，请从浏览器地址栏整段复制。")
    return {
        "courseId": course_id,
        "homeworkId": homework_id,
        "paperId": paper_id,
        "examId": exam_id,
        "route": text.split("#")[0],
    }


def candidate_terms():
    now = datetime.now()
    year, month = now.year, now.month
    if month >= 8:
        ordered = [int(f"{year + 1}1"), int(f"{year}2"), int(f"{year}1")]
    elif month <= 2:
        ordered = [int(f"{year}1"), int(f"{year}2"), int(f"{year - 1}1")]
    else:
        ordered = [int(f"{year}2"), int(f"{year}1"), int(f"{year + 1}1")]
    terms = []
    for item in ordered:
        if item not in terms:
            terms.append(item)
    return terms


def polymas_identity(cookie_text):
    jar = parse_cookie(cookie_text or "")
    token = jar.get("polymas-token") or jar.get("ai-poly") or ""
    raw = unquote(jar.get("AI-POLY-UINFO") or "")
    student_id = ""
    if raw:
        try:
            student_id = str(json.loads(raw).get("nid") or "")
        except json.JSONDecodeError:
            student_id = ""
    return token, student_id


def _polymas_headers(token, route):
    headers = dict(HEADERS)
    headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": POLY_ORIGIN,
            "Referer": POLY_ORIGIN + "/",
            "authorization": token,
            "route": route,
        }
    )
    return headers


def _polymas_options(quest):
    options = []
    blanks = []
    for option in quest.get("optionList") or []:
        text = strip_html(option.get("content"))
        letter = str(option.get("orderNo") or "").strip()
        if not text:
            if letter:
                blanks.append(letter if letter.startswith("【") else f"【{letter}】")
            continue
        if text in _JUDGEMENT:
            options.append(text)
            continue
        if letter.isdigit():
            options.append(format_choice(text, int(letter) - 1))
            continue
        if letter and not text.startswith(letter):
            text = f"{letter}. {text}"
        options.append(format_choice(text, len(options)))
    return options, blanks


def _walk_polymas(quests, group_title, out):
    for quest in quests or []:
        stem = strip_html(quest.get("content") or quest.get("questionName"))
        options, blanks = _polymas_options(quest)
        if stem or options or blanks:
            out.append(
                {
                    "type": quest.get("questionTypeName") or group_title or "未知题型",
                    "stem": stem,
                    "options": options,
                    "blankLabels": blanks,
                    "score": quest.get("score") if quest.get("score") is not None else "",
                }
            )
        _walk_polymas(quest.get("childList") or [], group_title, out)


def parse_polymas_exam(payload, title):
    paper = ((payload or {}).get("data") or {}).get("paperContent") or {}
    questions = []
    for group in paper.get("groupList") or []:
        _walk_polymas(group.get("questList") or [], group.get("title") or "", questions)
    if not questions:
        raise RuntimeError("这份作业没有题目。")
    for index, question in enumerate(questions, start=1):
        question["n"] = index
        question["blankLabels"] = infer_blank_labels(question)
    return {
        "course": "",
        "title": title or "作业",
        "total_score": paper.get("totalScore") or "",
        "questions": questions,
    }


def fetch_polymas(url, cookie=None):
    meta = parse_polymas_url(url)
    token, student_id = polymas_identity(cookie if cookie is not None else COOKIE)
    if not token or not student_id:
        raise RuntimeError("还没有读到 AI 教学中心的登录。请点「切换账号」，在弹出的窗口重新登录后再获取答案。")
    client = session()
    headers = _polymas_headers(token, meta["route"])
    last_message = ""
    for term in candidate_terms():
        body = {
            "homeworkId": meta["homeworkId"],
            "studentId": student_id,
            "paperId": meta["paperId"],
            "examId": meta["examId"],
            "courseId": meta["courseId"],
            "term": term,
        }
        response = client.post(POLY_EXAM_API, headers=headers, json=body, timeout=20)
        if response.status_code in (401, 403):
            raise RuntimeError("登录已失效。请点「切换账号」，在弹出的窗口重新登录后再获取答案。")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"拉题目失败：服务器返回的不是题目数据（HTTP {response.status_code}）。") from exc
        if payload.get("code") != 200:
            last_message = str(payload.get("msg") or payload.get("message") or payload.get("code") or "")
            if "登录" in last_message or "token" in last_message.lower() or "未授权" in last_message:
                raise RuntimeError("登录已失效。请点「切换账号」，在弹出的窗口重新登录后再获取答案。")
            continue
        paper = (payload.get("data") or {}).get("paperContent") or {}
        if not paper.get("groupList"):
            continue
        title = _polymas_title(client, headers, meta, term)
        return parse_polymas_exam(payload, title)
    if last_message:
        raise RuntimeError("拉题目失败：" + last_message)
    raise RuntimeError("没有拉到这门课的题目。请确认地址是正在做的作业页，并且登录的是做这份作业的账号。")


def _polymas_title(client, headers, meta, term):
    try:
        response = client.post(
            POLY_DETAIL_API,
            headers=headers,
            json={"term": term, "courseId": meta["courseId"], "homeworkId": meta["homeworkId"]},
            timeout=20,
        )
        data = response.json().get("data") or {}
    except (ValueError, requests.RequestException):
        return ""
    return str(data.get("homeworkName") or data.get("title") or "")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.has_img = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            self.has_img = True

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(raw):
    parser = _TextExtractor()
    parser.feed(str(raw or ""))
    text = re.sub(r"\s+", " ", "".join(parser.parts).replace("\xa0", " ")).strip()
    if parser.has_img:
        text += "（题目含图片，仅按文字作答）"
    return text


_CHOICE_LETTERS = "ABCDEFGH"
_JUDGEMENT = {"对", "错", "正确", "错误", "是", "否", "√", "×"}


def format_choice(text, index):
    text = str(text or "").strip()
    if not text:
        return ""
    match = re.match(r"^([A-Ha-h])\s*[\.、．:：]\s*(.*)$", text)
    if match:
        body = match.group(2).strip()
        letter = match.group(1).upper()
        return f"{letter}. {body}" if body else letter
    if text in _JUDGEMENT:
        return text
    if 0 <= index < len(_CHOICE_LETTERS):
        return f"{_CHOICE_LETTERS[index]}. {text}"
    return text


def normalize_question(question):
    raw_name = str(question.get("name") or "")
    qtype = question.get("questionType") or {}
    options = []
    for index, opt in enumerate(question.get("questionOptions") or []):
        content = format_choice(strip_html(opt.get("content")), index)
        if content:
            options.append(content)
    return {
        "type": qtype.get("name") or "未知题型",
        "stem": strip_html(raw_name),
        "options": options,
        "score": question.get("questionScore") or "",
    }


def collect_questions(nodes, bucket):
    for question in nodes or []:
        children = question.get("questionChildrens")
        if isinstance(children, list) and children:
            collect_questions(children, bucket)
            continue
        item = normalize_question(question)
        if item["stem"]:
            bucket.append(item)


def parse_exam(data):
    exam = (data or {}).get("rt") or {}
    exam = exam.get("examBase") if isinstance(exam, dict) else None
    parts = exam.get("workExamParts") if isinstance(exam, dict) else None
    if not isinstance(parts, list):
        return None
    questions = []
    for part in parts:
        collect_questions(part.get("questionDtos"), questions)
    for index, question in enumerate(questions, start=1):
        question["n"] = index
        question["blankLabels"] = infer_blank_labels(question)
    if not questions:
        return None
    return {
        "title": exam.get("name") or "作业",
        "course": exam.get("courseName") or "",
        "questions": questions,
    }


def merge_cookie(cookie_text, response):
    jar = parse_cookie(str(cookie_text or ""))
    for item in response.cookies:
        jar[item.name] = item.value
    return "; ".join(f"{key}={value}" for key, value in jar.items())


def request_with_sso(method, url, cookie_text, headers=None, data=None, timeout=30):
    """作业接口会先跳到登录页再跳回来。把这几跳走完，不要当成登录失效。"""
    client = session()
    cookie_text = str(cookie_text or "")
    current = url
    verb = method.upper()
    body = data
    base_headers = dict(headers or {})
    response = None
    for _ in range(7):
        hdrs = dict(base_headers)
        if verb == "GET":
            hdrs = {
                "User-Agent": base_headers.get("User-Agent", HEADERS["User-Agent"]),
                "Accept": "*/*",
            }
        if cookie_text:
            hdrs["Cookie"] = cookie_text
        response = client.request(
            verb,
            current,
            headers=hdrs,
            data=body if verb != "GET" else None,
            timeout=timeout,
            allow_redirects=False,
        )
        cookie_text = merge_cookie(cookie_text, response)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response, cookie_text
        location = response.headers.get("location") or ""
        if not location:
            return response, cookie_text
        nxt = urljoin(response.url, location)
        host = urlparse(nxt).netloc.lower()
        if not (host.endswith("zhihuishu.com") or host.endswith("polymas.com")):
            return response, cookie_text
        if verb != "GET" and response.status_code in (301, 302, 303):
            verb = "GET"
            body = None
        current = nxt
    return response, cookie_text


def _login_wall(response):
    if response is None:
        return True
    if response.status_code in (301, 302, 303, 307, 308):
        return True
    return urlparse(response.url).netloc.lower().startswith("passport.")


def fetch_exam(url, cookie=None):
    cookie_text = COOKIE if cookie is None else str(cookie).strip()
    if not cookie_text:
        raise RuntimeError("请先填写 Cookie。在已登录的浏览器里打开作业页，从 F12 复制请求头中的 Cookie。")
    payload = parse_homework_url(url)
    secret = encrypt_params(payload)
    resp, cookie_text = request_with_sso(
        "POST",
        HOMEWORK_URL,
        cookie_text,
        headers=HEADERS,
        data={"secretStr": secret},
        timeout=30,
    )
    if _login_wall(resp) or getattr(resp.request, "method", "POST") != "POST":
        resp, _cookie_text = request_with_sso(
            "POST",
            HOMEWORK_URL,
            cookie_text,
            headers=HEADERS,
            data={"secretStr": secret},
            timeout=30,
        )
    if _login_wall(resp):
        raise RuntimeError("登录已失效。请点「切换账号」重新登录后再获取答案。")
    text = resp.text or ""
    try:
        data = resp.json()
    except ValueError:
        snippet = re.sub(r"\s+", " ", text)[:180]
        raise RuntimeError(f"接口没有返回题目 JSON（HTTP {resp.status_code}）：{snippet}")
    status = str(data.get("status"))
    if status != "200":
        message = data.get("msg") or data.get("message") or text[:180]
        if data.get("code") == -12 or "验证" in str(message):
            raise RuntimeError("网站要求验证码。先在浏览器里打开这个作业页通过验证，再重新运行。")
        if any(word in str(message) for word in ("登录", "登陆", "未登录", "失效")) or resp.status_code in (401, 403):
            raise RuntimeError(
                "登录已失效。请在弹出的窗口重新登录智慧树后再试。"
                f"（接口提示：{message}）"
            )
        if str(message) == "1":
            raise RuntimeError(
                "这份作业不属于当前登录账号。请用浏览器里正在打开这份作业的账号，再点获取答案。"
            )
        if "参数" in str(message):
            raise RuntimeError(
                "服务器没有认出这条作业地址。请回到正在做题的页面，重新复制地址栏整段地址后再试。"
            )
        raise RuntimeError(f"拉题目失败：{message}")
    exam = parse_exam(data)
    if not exam:
        raise RuntimeError("登录状态有效，但这份响应里没有题目。确认地址是正在做的作业页。")
    return exam


def load_api_key():
    path = ROOT / "apikey.txt"
    if not path.exists():
        raise RuntimeError("缺少 apikey.txt。把 DeepSeek Key 单独放在这一行。")
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError("apikey.txt 是空的。")
    return key


def infer_blank_labels(question):
    labels = [str(item).strip() for item in (question.get("blankLabels") or []) if str(item).strip()]
    if labels:
        return labels
    stem = question.get("stem") or ""
    marks = re.findall(r"_{2,}", stem)
    if marks:
        return [f"【{index}】" for index in range(1, len(marks) + 1)]
    if "填空" in str(question.get("type") or ""):
        return ["【1】"]
    return []


def split_blank_answers(texts, count):
    if count <= 1:
        return (texts[:1] or [""])
    if len(texts) == count:
        return texts
    if len(texts) == 1:
        for pattern in (r"[;；|｜]", r"[、,，]"):
            pieces = [item.strip() for item in re.split(pattern, texts[0]) if item.strip()]
            if len(pieces) == count:
                return pieces
    padded = list(texts) + [""] * count
    return padded[:count]


def answer_parts(question):
    texts = answer_list(question.get("modelAnswer"))
    labels = question.get("blankLabels") or []
    if not labels:
        return [{"label": "", "text": "、".join(texts)}]
    texts = split_blank_answers(texts, len(labels))
    return [{"label": label, "text": text} for label, text in zip(labels, texts)]


def build_prompt(questions):
    blocks = []
    for question in questions:
        lines = [f"{question['n']}. [{question['type']}] {question['stem']}"]
        labels = question.get("blankLabels") or []
        if question["options"]:
            lines.extend(f"- {opt}" for opt in question["options"])
        elif labels:
            lines.append(f"（共 {len(labels)} 个空，answer 按 {'、'.join(labels)} 的顺序各放一个字符串）")
        else:
            lines.append("（无选项，请直接作答）")
        blocks.append("\n".join(lines))
    return "\n".join(
        [
            "根据下面的题目作答。只输出一个 JSON 对象，不要 Markdown。",
            '格式：{"answers":[{"n":1,"answer":["选项原文"],"reason":"不超过40字"}]}',
            "规则：",
            "1. 选择题的 answer 必须逐字复制选项原文。单选只放 1 个，多选放全部正确项。",
            "2. 判断题 answer 使用选项原文；没有选项时用「对」或「错」。",
            "3. 填空题有几个空，answer 里就放几个字符串，按空的顺序一一对应，不要合并成一句。简答只放一个字符串。",
            "4. n 使用题目给出的题号。",
            "",
            "\n\n".join(blocks),
        ]
    )


def parse_model_json(text):
    trimmed = str(text or "").strip()
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", trimmed)
    if fence:
        return json.loads(fence.group(1))
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start >= 0 and end > start:
        return json.loads(trimmed[start : end + 1])
    raise RuntimeError("模型没有返回 JSON")


def deepseek_ip():
    global _PINNED_IP
    if _PINNED_IP:
        return _PINNED_IP
    with _PINNED_LOCK:
        if _PINNED_IP:
            return _PINNED_IP
        ips = [ip for ip in deepseek_addresses() if ip]
        _PINNED_IP = ips[0] if ips else ""
        return _PINNED_IP


@contextmanager
def pinned_deepseek():
    import urllib3.util.connection as urllib3_cn

    ip = deepseek_ip() or None
    original = urllib3_cn.create_connection

    def create_connection(address, *args, **kwargs):
        host, port = address
        if ip and host == "api.deepseek.com":
            address = (ip, port)
        return original(address, *args, **kwargs)

    urllib3_cn.create_connection = create_connection
    try:
        yield
    finally:
        urllib3_cn.create_connection = original


threading.Thread(target=deepseek_ip, name="deepseek-pin", daemon=True).start()
_DEEPSEEK_LOCAL = threading.local()


def deepseek_session():
    client = getattr(_DEEPSEEK_LOCAL, "client", None)
    if client is None:
        client = session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1)
        client.mount("https://", adapter)
        _DEEPSEEK_LOCAL.client = client
    return client


def find_provider(provider_id):
    for item in PROVIDERS:
        if item["id"] == provider_id:
            return item
    return PROVIDERS[0]


def resolve_provider(provider_id, model, base_url):
    found = find_provider(provider_id)
    endpoint = provider_endpoint(found, base_url)
    chosen = str(model or "").strip() or found["model"]
    if not endpoint.startswith(("http://", "https://")):
        raise RuntimeError("接口地址需要以 http:// 或 https:// 开头。")
    if not chosen:
        raise RuntimeError("请填写模型名称。")
    return found, endpoint, chosen


def provider_endpoint(found, base_url):
    typed = str(base_url or "").strip()
    if found["id"] in ("custom", "ollama", "lmstudio", "doubao"):
        return typed or found["url"]
    return found["url"] or typed


def _model_list_urls(endpoint):
    root = str(endpoint or "").strip().rstrip("/")
    if root.endswith("/chat/completions"):
        root = root[: -len("/chat/completions")]
    urls = [root + "/models"]
    if "11434" in root:
        urls.append("http://127.0.0.1:11434/api/tags")
    if "generativelanguage.googleapis.com" in root:
        urls.append("https://generativelanguage.googleapis.com/v1beta/models")
    return urls


def _collect_model_names(payload):
    names = []

    def add(value):
        text = str(value or "").strip()
        if text.startswith("models/"):
            text = text.split("/", 1)[1]
        if text and text not in names:
            names.append(text)

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(item.get("id") or item.get("name") or item.get("model"))
        return names
    if not isinstance(payload, dict):
        return names
    buckets = [payload.get("data"), payload.get("models")]
    output = payload.get("output")
    if isinstance(output, dict):
        buckets.append(output.get("models") or output.get("data"))
    for bucket in buckets:
        if isinstance(bucket, list):
            names.extend(_collect_model_names(bucket))
        elif isinstance(bucket, dict):
            names.extend(_collect_model_names(bucket.get("models") or bucket.get("data") or []))
    return names


def list_models(provider_id, base_url, api_key):
    found = find_provider(provider_id)
    endpoint = provider_endpoint(found, base_url)
    if not endpoint.startswith(("http://", "https://")):
        raise RuntimeError("接口地址需要以 http:// 或 https:// 开头。")
    if found["needsKey"] and not str(api_key or "").strip():
        raise RuntimeError(f"请先填写{found['name']}自己的 API Key。现在用的如果是别的厂商的 Key，列表会失败。")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-goog-api-key"] = api_key
    last_error = "这个接口没有返回模型名称。"
    for url in _model_list_urls(endpoint):
        try:
            response = session().get(url, headers=headers, timeout=20)
        except requests.RequestException:
            last_error = f"连不上{found['name']}的模型列表。请检查网络，本地模型要先启动。"
            continue
        try:
            payload = response.json()
        except ValueError:
            last_error = f"模型列表不是 JSON（HTTP {response.status_code}）。"
            continue
        if not response.ok:
            message = ""
            if isinstance(payload, dict):
                message = str(((payload.get("error") or {}).get("message")) or payload.get("msg") or "")
            last_error = "获取模型列表失败：" + (message or response.text[:200])
            continue
        names = _collect_model_names(payload)
        if names:
            return names
    if found["id"] == "doubao":
        raise RuntimeError("豆包没有公开模型目录。请在火山方舟复制接入点 ID，填到模型名称。")
    raise RuntimeError(last_error)


def probe_connection(provider_id, model, base_url, api_key):
    found, endpoint, chosen = resolve_provider(provider_id, model, base_url)
    if found["needsKey"] and not str(api_key or "").strip():
        raise RuntimeError(f"请先填写{found['name']}的 API Key，再测试连接。")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-goog-api-key"] = api_key
    payload = {
        "model": chosen,
        "temperature": 0,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "只回复OK"}],
    }
    try:
        response = session().post(endpoint, headers=headers, json=payload, timeout=(8, 40))
    except requests.RequestException as exc:
        raise RuntimeError(f"连不上{found['name']}。请检查网络、接口地址，本地模型要先启动。") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{found['name']} 没有返回 JSON（HTTP {response.status_code}）。") from exc
    if not response.ok:
        message = ""
        if isinstance(data, dict):
            message = str(((data.get("error") or {}).get("message")) or data.get("msg") or "")
        raise RuntimeError(f"{found['name']} {response.status_code}：" + (message or response.text[:200]))
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) if isinstance(data, dict) else ""
    if content is None and isinstance(data, dict):
        content = ""
    return {"name": found["name"], "model": chosen, "reply": str(content or "").strip()[:40]}


def ask_chunk(api_key, questions, endpoint=None, model=None, provider_name="DeepSeek"):
    endpoint = endpoint or API_BASE
    model = model or MODEL
    label = provider_name or "模型"
    use_json_format = True
    resp = None
    for attempt in range(3):
        payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 2500,
            "messages": [
                {"role": "system", "content": "你只根据题目和选项作答，并且只输出 JSON。"},
                {"role": "user", "content": build_prompt(questions)},
            ],
        }
        if use_json_format:
            payload["response_format"] = {"type": "json_object"}
        if "deepseek" in str(model or "").lower() or "api.deepseek.com" in str(endpoint):
            payload["thinking"] = {"type": "disabled"}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            resp = deepseek_session().post(endpoint, headers=headers, json=payload, timeout=(12, 120))
        except (requests.Timeout, requests.ConnectionError):
            resp = None
            continue
        if resp is not None and resp.status_code == 400 and use_json_format:
            use_json_format = False
            continue
        if resp is not None and resp.status_code == 429 and attempt < 2:
            time.sleep(1.2)
            continue
        break
    if resp is None:
        raise RuntimeError(f"连不上{label}。请检查网络、接口地址，本地模型要先在本机启动。")
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"{label} 返回的不是 JSON（HTTP {resp.status_code}）")
    if not resp.ok:
        message = ((data.get("error") or {}).get("message")) or resp.text[:300]
        raise RuntimeError(f"{label} {resp.status_code}：{message}")
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    parsed = parse_model_json(content)
    answers = parsed.get("answers") if isinstance(parsed, dict) else None
    if not isinstance(answers, list):
        return []
    cleaned = []
    for item in answers:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "n": int(item.get("n") or 0),
                "answer": item.get("answer"),
                "reason": item.get("reason") or "",
            }
        )
    return cleaned


def answer_list(raw):
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    pieces = [item.strip() for item in re.split(r"[、,，;；]", text) if item.strip()]
    return pieces or [text]


def _compact(text):
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _option_letter(option):
    match = re.match(r"^\s*([A-Ha-h])\s*[\.、．:：]", str(option))
    return match.group(1).upper() if match else ""


def _option_body(option):
    return re.sub(r"^\s*[A-Ha-h]\s*[\.、．:：]\s*", "", str(option)).strip()


def align_to_options(options, raw):
    pieces = answer_list(raw)
    if not options or not pieces:
        return pieces
    chosen = []

    def add(option):
        if option not in chosen:
            chosen.append(option)

    for piece in pieces:
        compact = _compact(piece)
        stripped = piece.strip()
        if re.fullmatch(r"[A-Ha-h]", stripped):
            for option in options:
                if _option_letter(option) == stripped.upper():
                    add(option)
            continue
        if re.fullmatch(r"[A-Ha-h]{2,8}", stripped):
            for char in stripped.upper():
                for option in options:
                    if _option_letter(option) == char:
                        add(option)
            continue
        exact = []
        fuzzy = []
        for option in options:
            body = _compact(_option_body(option))
            full = _compact(option)
            if compact and (compact == full or compact == body):
                exact = [option]
                break
            if len(compact) >= 4 and body and (compact in body or body in compact):
                fuzzy.append(option)
        if exact:
            add(exact[0])
        elif len(fuzzy) == 1:
            add(fuzzy[0])
    return chosen or pieces


def question_chunks(questions, size=CHUNK):
    for start in range(0, len(questions), size):
        yield questions[start : start + size]


def apply_answers(exam, found):
    for question in exam["questions"]:
        item = found.get(question["n"])
        question["modelAnswer"] = align_to_options(
            question.get("options") or [],
            item["answer"] if item else [],
        )
        question["reason"] = item["reason"] if item else ""
    return exam


def collect_answers(api_key, jobs, on_progress=None):
    found = {}
    if not jobs:
        return found
    workers = min(PARALLEL, len(jobs))

    def remember(chunk, items):
        for item in items:
            found.setdefault(item["n"], item)
        if on_progress:
            on_progress(f"已解答第 {chunk[0]['n']}-{chunk[-1]['n']} 题")

    with pinned_deepseek():
        if workers == 1:
            chunk = jobs[0]
            if on_progress:
                on_progress(f"正在解答第 {chunk[0]['n']}-{chunk[-1]['n']} 题…")
            remember(chunk, ask_chunk(api_key, chunk))
            return found
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for chunk in jobs:
                if on_progress:
                    on_progress(f"正在解答第 {chunk[0]['n']}-{chunk[-1]['n']} 题…")
                futures[pool.submit(ask_chunk, api_key, chunk)] = chunk
            for future in as_completed(futures):
                remember(futures[future], future.result())
    return found


def solve(exam, api_key=None, on_progress=None):
    api_key = str(api_key or "").strip() or load_api_key()
    found = collect_answers(api_key, list(question_chunks(exam["questions"])), on_progress=on_progress)
    return apply_answers(exam, found)


def fetch_homework(url, cookie=None):
    if is_polymas_url(url):
        return fetch_polymas(url, cookie=cookie)
    return fetch_exam(url, cookie=cookie)


def render(exam):
    head = exam["title"]
    if exam["course"]:
        head = f"{exam['course']} · {head}"
    lines = [f"{head} · {len(exam['questions'])} 题", ""]
    for question in exam["questions"]:
        score = f" · {question['score']}分" if question["score"] != "" else ""
        lines.append(f"{question['n']}. [{question['type']}{score}] {question['stem']}")
        parts = answer_parts(question)
        if question.get("blankLabels"):
            for part in parts:
                lines.append(f"{part['label']} {part['text'] or '（无）'}")
        else:
            lines.append("答案：" + (parts[0]["text"] if parts and parts[0]["text"] else "（无）"))
        if question.get("reason"):
            lines.append("理由：" + str(question["reason"]))
        lines.append("")
    lines.append("答案由 DeepSeek 生成，提交前请自行核对。程序不会交卷。")
    return "\n".join(lines).rstrip() + "\n"


def split_homework_urls(text):
    found = []
    seen = set()
    for piece in re.split(r"[\s,，;；]+", str(text or "").strip()):
        piece = piece.strip()
        if not piece or piece in seen:
            continue
        seen.add(piece)
        found.append(piece)
    return found


def answer_filename(index, exam):
    head = exam.get("title") or "作业"
    if exam.get("course"):
        head = f"{exam['course']} · {head}"
    head = re.sub(r'[<>:"/\\|?*\r\n]', " ", head)
    head = re.sub(r"\s+", " ", head).strip(" .")[:50] or "作业"
    return f"{index:02d}-{head}.txt"


def result_payload(exam, folder=None, index=1, save=True):
    text = render(exam)
    out = None
    if save:
        if folder:
            out_dir = Path(folder)
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / answer_filename(index, exam)
        else:
            out = ROOT / "答案.txt"
        out.write_text(text, encoding="utf-8")
    return {
        "course": exam["course"],
        "title": exam["title"],
        "text": text,
        "path": str(out) if out else "",
        "file": out.name if out else "",
        "questions": [
            {
                "n": question["n"],
                "type": question["type"],
                "score": str(question["score"]),
                "stem": question["stem"],
                "options": question["options"],
                "answer": "、".join(part["text"] for part in answer_parts(question) if part["text"]),
                "parts": answer_parts(question),
                "reason": question.get("reason") or "",
            }
            for question in exam["questions"]
        ],
    }


def run(url, cookie=None, api_key=None, on_progress=None, folder=None, index=1):
    if on_progress:
        on_progress("正在拉取题目…")
    if is_polymas_url(url):
        exam = fetch_polymas(url, cookie=cookie)
    else:
        exam = fetch_exam(url, cookie=cookie)
    message = f"共 {len(exam['questions'])} 题"
    print(message, flush=True)
    if on_progress:
        on_progress(message)
    solve(exam, api_key=api_key, on_progress=on_progress)
    return result_payload(exam, folder=folder, index=index)


def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("请输入作业页地址：").strip()
    if not url:
        raise SystemExit("没有输入地址。")
    result = run(url)
    print(result["text"])
    print(f"已写入 {result['path']}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc))
