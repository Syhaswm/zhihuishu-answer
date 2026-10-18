"""输入智慧树作业页地址，拉取题目后用 DeepSeek 返回答案。

不会交卷。Cookie 过期后，在已登录的浏览器里打开作业页，
从 F12 复制整段 Cookie，替换下面的 COOKIE。
通常要更新的是 CASTGC、jt-cas、CASLOGC、JSESSIONID、acw_tc、SERVERID。
"""

import json
import re
import sys
from base64 import b64encode
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

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
MODEL = "deepseek-chat"
ROOT = Path(__file__).resolve().parent


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
            "这不是作业做题页地址。请粘贴浏览器里打开作业后的完整地址，"
            "路径里需要包含 /webExamList/dohomework/。"
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


def normalize_question(question):
    raw_name = str(question.get("name") or "")
    qtype = question.get("questionType") or {}
    options = []
    for opt in question.get("questionOptions") or []:
        content = strip_html(opt.get("content"))
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
    if not questions:
        return None
    return {
        "title": exam.get("name") or "作业",
        "course": exam.get("courseName") or "",
        "questions": questions,
    }


def fetch_exam(url, cookie=None):
    cookie_text = COOKIE if cookie is None else str(cookie).strip()
    if not cookie_text:
        raise RuntimeError("请先填写 Cookie。在已登录的浏览器里打开作业页，从 F12 复制请求头中的 Cookie。")
    payload = parse_homework_url(url)
    secret = encrypt_params(payload)
    resp = session().post(
        HOMEWORK_URL,
        headers=HEADERS,
        cookies=parse_cookie(cookie_text),
        data={"secretStr": secret},
        timeout=30,
        allow_redirects=False,
    )
    if resp.status_code in (301, 302, 303, 307, 308):
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


def build_prompt(questions):
    blocks = []
    for question in questions:
        lines = [f"{question['n']}. [{question['type']}] {question['stem']}"]
        if question["options"]:
            lines.extend(f"- {opt}" for opt in question["options"])
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
            "3. 填空、简答把答案放进 answer 数组，只放一个字符串。",
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


def ask_chunk(api_key, questions):
    resp = session().post(
        API_BASE,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "temperature": 0.1,
            "max_tokens": 2500,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "你只根据题目和选项作答，并且只输出 JSON。"},
                {"role": "user", "content": build_prompt(questions)},
            ],
        },
        timeout=120,
    )
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"DeepSeek 返回的不是 JSON（HTTP {resp.status_code}）")
    if not resp.ok:
        message = ((data.get("error") or {}).get("message")) or resp.text[:300]
        raise RuntimeError(f"DeepSeek {resp.status_code}：{message}")
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


def solve(exam, api_key=None, on_progress=None):
    api_key = str(api_key or "").strip() or load_api_key()
    questions = exam["questions"]
    found = {}
    size = 10
    for start in range(0, len(questions), size):
        chunk = questions[start : start + size]
        message = f"正在解答第 {chunk[0]['n']}-{chunk[-1]['n']} 题…"
        print(message, flush=True)
        if on_progress:
            on_progress(message)
        for item in ask_chunk(api_key, chunk):
            found[item["n"]] = item
    for question in questions:
        item = found.get(question["n"])
        question["modelAnswer"] = item["answer"] if item else []
        question["reason"] = item["reason"] if item else ""
    return exam


def render(exam):
    head = exam["title"]
    if exam["course"]:
        head = f"{exam['course']} · {head}"
    lines = [f"{head} · {len(exam['questions'])} 题", ""]
    for question in exam["questions"]:
        score = f" · {question['score']}分" if question["score"] != "" else ""
        lines.append(f"{question['n']}. [{question['type']}{score}] {question['stem']}")
        answers = answer_list(question.get("modelAnswer"))
        lines.append("答案：" + ("、".join(answers) if answers else "（无）"))
        if question.get("reason"):
            lines.append("理由：" + str(question["reason"]))
        lines.append("")
    lines.append("答案由 DeepSeek 生成，提交前请自行核对。程序不会交卷。")
    return "\n".join(lines).rstrip() + "\n"


def result_payload(exam):
    text = render(exam)
    out = ROOT / "答案.txt"
    out.write_text(text, encoding="utf-8")
    return {
        "course": exam["course"],
        "title": exam["title"],
        "text": text,
        "path": str(out),
        "questions": [
            {
                "n": question["n"],
                "type": question["type"],
                "score": str(question["score"]),
                "stem": question["stem"],
                "options": question["options"],
                "answer": "、".join(answer_list(question.get("modelAnswer"))),
                "reason": question.get("reason") or "",
            }
            for question in exam["questions"]
        ],
    }


def run(url, cookie=None, api_key=None, on_progress=None):
    if on_progress:
        on_progress("正在拉取题目…")
    exam = fetch_exam(url, cookie=cookie)
    message = f"共 {len(exam['questions'])} 题"
    print(message, flush=True)
    if on_progress:
        on_progress(message)
    solve(exam, api_key=api_key, on_progress=on_progress)
    return result_payload(exam)


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
