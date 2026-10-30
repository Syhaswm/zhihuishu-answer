"""Create release on Gitee and GitHub, upload Setup.exe (and optional extra assets)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "installer" / "智慧树答题-Setup.exe"
OWNER = "Syhaswm"
REPO = "zhihuishu-answer"
GITHUB = f"{OWNER}/{REPO}"


def http_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}
    return session


def load_gitee_token() -> str:
    cred = Path.home() / ".git-credentials"
    if not cred.exists():
        raise SystemExit("缺少 ~/.git-credentials")
    text = cred.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if "gitee.com" not in line:
            continue
        match = re.search(r"https://[^:]+:([^@]+)@gitee\.com", line)
        if match:
            return match.group(1)
    raise SystemExit("在 git-credentials 中未找到 gitee token")


def gh_release_exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "-R", GITHUB],
        capture_output=True,
    )
    return result.returncode == 0


def publish_gitee(tag: str, body: str, setup: Path = SETUP) -> None:
    if not setup.is_file():
        raise SystemExit(f"缺少安装包: {setup}")

    token = load_gitee_token()
    session = http_session()
    api = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}/releases"
    response = session.post(
        api,
        params={"access_token": token},
        json={"tag_name": tag, "name": tag, "body": body, "target_commitish": "main"},
        timeout=60,
    )
    if response.status_code == 400 and "already exists" in response.text.lower():
        print("gitee release exists, fetch id")
        listed = session.get(api, params={"access_token": token, "per_page": 100}, timeout=60)
        listed.raise_for_status()
        release = next((item for item in listed.json() if item.get("tag_name") == tag), None)
        if not release:
            raise SystemExit("找不到已有 Gitee release")
        release_id = release["id"]
    else:
        response.raise_for_status()
        release_id = response.json()["id"]

    upload = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}/releases/{release_id}/attach_files"
    with setup.open("rb") as handle:
        uploaded = session.post(
            upload,
            params={"access_token": token},
            files={"file": (setup.name, handle, "application/octet-stream")},
            timeout=600,
        )
    uploaded.raise_for_status()
    print("gitee uploaded", setup.name, setup.stat().st_size)
    print(f"https://gitee.com/{OWNER}/{REPO}/releases/tag/{tag}")


def publish_github(
    tag: str,
    body: str,
    assets: list[Path] | None = None,
    upload_names: dict[Path, str] | None = None,
) -> None:
    paths = list(assets or [SETUP])
    names = upload_names or {}
    gh_assets: list[str] = []
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"缺少文件: {path}")
        display = names.get(path) or path.name
        gh_assets.append(f"{path}#{display}" if display != path.name else str(path))

    if gh_release_exists(tag):
        command = ["gh", "release", "upload", tag, "-R", GITHUB, "--clobber", *gh_assets]
        subprocess.run(command, check=True)
        print("github uploaded to existing release", tag)
    else:
        command = [
            "gh",
            "release",
            "create",
            tag,
            "-R",
            GITHUB,
            "--title",
            tag,
            "--notes",
            body,
            *gh_assets,
        ]
        subprocess.run(command, check=True)
        print("github created release", tag)
    print(f"https://github.com/{GITHUB}/releases/tag/{tag}")


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "v1.8.5"
    body = (
        sys.argv[2]
        if len(sys.argv) > 2
        else f"## {tag}\n\n- 与 Gitee 发行版同步\n"
    )
    publish_gitee(tag, body)
    publish_github(tag, body)


if __name__ == "__main__":
    main()
