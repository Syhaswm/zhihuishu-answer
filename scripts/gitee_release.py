"""Create Gitee release and upload Setup.exe (one-off helper)."""
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "installer" / "智慧树答题-Setup.exe"
OWNER = "Syhaswm"
REPO = "zhihuishu-answer"


def load_token() -> str:
    cred = Path.home() / ".git-credentials"
    if not cred.exists():
        raise SystemExit("缺少 ~/.git-credentials")
    text = cred.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if "gitee.com" not in line:
            continue
        m = re.search(r"https://[^:]+:([^@]+)@gitee\.com", line)
        if m:
            return m.group(1)
    raise SystemExit("在 git-credentials 中未找到 gitee token")


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1.7.8"
    version = tag.lstrip("v")
    body = sys.argv[2] if len(sys.argv) > 2 else f"## {tag}\n\n- 贴边窗口透明度：不透明 / 95% / 90% / 85%（Windows）\n- 恢复常规窗口自动回到不透明\n"
    if not SETUP.is_file():
        raise SystemExit(f"缺少安装包: {SETUP}")

    token = load_token()
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}

    api = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}/releases"
    r = session.post(
        api,
        params={"access_token": token},
        json={"tag_name": tag, "name": tag, "body": body, "target_commitish": "main"},
        timeout=60,
    )
    if r.status_code == 400 and "already exists" in r.text.lower():
        print("release exists, fetch id")
        r2 = session.get(api, params={"access_token": token, "per_page": 20}, timeout=60)
        r2.raise_for_status()
        rel = next((x for x in r2.json() if x.get("tag_name") == tag), None)
        if not rel:
            raise SystemExit("找不到已有 release")
        release_id = rel["id"]
    else:
        r.raise_for_status()
        release_id = r.json()["id"]
    print("release_id", release_id)

    upload = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}/releases/{release_id}/attach_files"
    with SETUP.open("rb") as f:
        ru = session.post(
            upload,
            params={"access_token": token},
            files={"file": (SETUP.name, f, "application/octet-stream")},
            timeout=600,
        )
    ru.raise_for_status()
    print("uploaded", SETUP.name, SETUP.stat().st_size)
    print(f"https://gitee.com/{OWNER}/{REPO}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
