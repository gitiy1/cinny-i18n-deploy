#!/usr/bin/env python3

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API_BASE = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
UPSTREAM_REPO = os.getenv("UPSTREAM_REPO", "Kx501/cinny-i18n")
UPSTREAM_REF = os.getenv("UPSTREAM_REF", "master")
TARGET_REPO = os.getenv("TARGET_REPO") or os.getenv("GITHUB_REPOSITORY")
DEPLOY_BRANCH = os.getenv("DEPLOY_BRANCH", "web")
MARKER_FILE = os.getenv("MARKER_FILE", ".cinny-i18n-upstream-sha")
TOKEN = os.getenv("GITHUB_TOKEN", "")


def github_get(path: str, allow_404: bool = False):
    url = f"{API_BASE}{path}"

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cinny-i18n-web-upstream-checker",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset)
            return json.loads(body)

    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None

        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API error {exc.code} for {url}: {body}") from exc


def get_upstream_sha() -> str:
    encoded_ref = urllib.parse.quote(UPSTREAM_REF, safe="")
    data = github_get(f"/repos/{UPSTREAM_REPO}/commits/{encoded_ref}")

    sha = str(data.get("sha", "")).strip()

    if not sha:
        raise RuntimeError(f"Could not find commit sha for {UPSTREAM_REPO}@{UPSTREAM_REF}")

    return sha


def get_deployed_sha() -> str:
    if not TARGET_REPO:
        return ""

    encoded_file = urllib.parse.quote(MARKER_FILE, safe="/")
    encoded_ref = urllib.parse.quote(DEPLOY_BRANCH, safe="")

    data = github_get(
        f"/repos/{TARGET_REPO}/contents/{encoded_file}?ref={encoded_ref}",
        allow_404=True,
    )

    if not data:
        return ""

    if data.get("encoding") != "base64":
        return ""

    content = data.get("content", "")

    if not content:
        return ""

    decoded = base64.b64decode(content).decode("utf-8", "replace").strip()

    if not decoded:
        return ""

    return decoded.splitlines()[0].strip()


def write_github_outputs(outputs: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")

    if not output_path:
        for key, value in outputs.items():
            print(f"{key}={value}")
        return

    with open(output_path, "a", encoding="utf-8") as file:
        for key, value in outputs.items():
            value = "" if value is None else str(value)

            if "\n" in value:
                delimiter = f"EOF_{key}"
                file.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                file.write(f"{key}={value}\n")


def main() -> None:
    upstream_sha = get_upstream_sha()
    deployed_sha = get_deployed_sha()

    should_build = "true" if upstream_sha != deployed_sha else "false"

    write_github_outputs(
        {
            "upstream_sha": upstream_sha,
            "upstream_short_sha": upstream_sha[:7],
            "deployed_sha": deployed_sha,
            "should_build": should_build,
        }
    )

    print(f"Upstream repo: {UPSTREAM_REPO}")
    print(f"Upstream ref: {UPSTREAM_REF}")
    print(f"Latest upstream SHA: {upstream_sha}")
    print(f"Currently deployed SHA: {deployed_sha or '<none>'}")
    print(f"Should build: {should_build}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
