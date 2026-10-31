"""Copy Gitee release notes and assets to GitHub (backfill or repair)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from publish_release import (  # noqa: E402
    GITHUB,
    OWNER,
    REPO,
    SETUP,
    http_session,
    publish_github,
)


def version_key(text: str) -> tuple[int, ...]:
    numbers: list[int] = []
    for part in str(text or "").replace("v", " ").replace("V", " ").replace(".", " ").split():
        if part.isdigit():
            numbers.append(int(part))
    return tuple(numbers[:3])


def list_gitee_releases() -> list[dict]:
    session = http_session()
    releases: list[dict] = []
    page = 1
    while True:
        response = session.get(
            f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}/releases",
            params={"page": page, "per_page": 100, "direction": "asc"},
            timeout=60,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return releases


def asset_is_setup(name: str, url: str) -> bool:
    name = str(name or "")
    url = str(url or "")
    if "Setup.exe" in name or name.endswith("Setup.exe"):
        return True
    return "Setup.exe" in url or "%E7%AD%94%E9%A2%98-Setup.exe" in url


def gitee_has_setup(meta: list) -> bool:
    for asset in meta:
        if asset_is_setup(str(asset.get("name") or ""), str(asset.get("browser_download_url") or "")):
            return True
    return False


def github_has_setup(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "-R", GITHUB, "--json", "assets"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    payload = json.loads(result.stdout or "{}")
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        if name in ("智慧树答题-Setup.exe", "Setup.exe"):
            return True
    return False


def github_sync_done(tag: str, meta: list) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "-R", GITHUB],
        capture_output=True,
    )
    if result.returncode != 0:
        return False
    if gitee_has_setup(meta):
        return github_has_setup(tag)
    return True


def mirror_cache_dir(tag: str) -> Path:
    folder = ROOT / "build" / "release_mirror" / tag
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def local_asset_path(folder: Path, tag: str, remote_name: str, url: str) -> tuple[Path, str]:
    """Save under ASCII paths; keep original display name for GitHub upload."""
    if asset_is_setup(remote_name, url):
        return folder / "Setup.exe", SETUP.name
    if remote_name.endswith(".zip"):
        return folder / f"{tag}.zip", remote_name
    if remote_name.endswith(".tar.gz"):
        return folder / f"{tag}.tar.gz", remote_name
    safe = re.sub(r'[<>:"/\\|?*]', "_", remote_name)
    return folder / safe, remote_name


def download_asset(session, url: str, dest: Path, min_bytes: int = 0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size >= max(min_bytes, 1):
        print("keep cached", dest.name, dest.stat().st_size)
        return
    with session.get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_content(256 * 1024):
                if chunk:
                    handle.write(chunk)
    if not dest.is_file() or dest.stat().st_size < min_bytes:
        raise SystemExit(
            f"下载失败或被安全软件删除: {dest.name}（{dest}）。"
            " 可在 GitHub 仓库 Actions 里运行「Mirror Gitee releases」在云端同步，无需关火绒。"
        )


def ensure_tags_on_github() -> None:
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("SKIP_GIT_PUSH"):
        return
    subprocess.run(["git", "fetch", "origin", "--tags"], cwd=str(ROOT), check=True)
    subprocess.run(["git", "push", "github", "--tags"], cwd=str(ROOT), check=True)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--skip-git"]
    only_tag = args[0].strip() if args else ""
    if "--skip-git" not in sys.argv[1:]:
        ensure_tags_on_github()
    else:
        os.environ.setdefault("SKIP_GIT_PUSH", "1")
    session = http_session()
    releases = list_gitee_releases()
    releases.sort(key=lambda item: version_key(str(item.get("tag_name") or "")))

    for release in releases:
        tag = str(release.get("tag_name") or "").strip()
        if not tag:
            continue
        if only_tag and tag != only_tag:
            continue
        meta = release.get("assets") or []
        if github_sync_done(tag, meta):
            print("skip (already on GitHub)", tag)
            continue

        body = str(release.get("body") or tag)
        folder = mirror_cache_dir(tag)
        paths: list[Path] = []
        upload_names: dict[Path, str] = {}
        for asset in meta:
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if not url:
                continue
            dest, display = local_asset_path(folder, tag, name, url)
            print("download", tag, display)
            min_size = 5_000_000 if display == SETUP.name else 1024
            download_asset(session, url, dest, min_bytes=min_size)
            paths.append(dest)
            upload_names[dest] = display
        if not paths:
            print("warn: no assets on Gitee for", tag)
            continue
        publish_github(tag, body, paths, upload_names)


if __name__ == "__main__":
    main()
