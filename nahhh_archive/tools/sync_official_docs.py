from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


LINK_RE = re.compile(r"^- \[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\): (?P<description>.+)$")
DEFAULT_LLM_PATH = Path("llms.txt")
DEFAULT_OUTPUT_DIR = Path("docs/vendor/official")
DEFAULT_TIMEOUT_S = 30


@dataclass(frozen=True)
class DocEntry:
    title: str
    url: str
    description: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-").lower()


def parse_llms(path: Path, *, docs_only: bool = True) -> list[DocEntry]:
    entries: list[DocEntry] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = LINK_RE.match(raw_line.strip())
        if not match:
            continue
        url = match.group("url")
        if docs_only and not url.startswith("https://docs.battlecode.cam/"):
            continue
        entries.append(
            DocEntry(
                title=match.group("title").strip(),
                url=url,
                description=match.group("description").strip(),
            )
        )
    return entries


def output_path_for(base_dir: Path, entry: DocEntry) -> Path:
    parsed = urlparse(entry.url)
    relative = parsed.path.lstrip("/")
    if not relative:
        relative = "index.md"
    relative_path = Path(relative)
    if relative_path.suffix.lower() not in {".md", ".txt"}:
        relative_path = relative_path / "index.md"
    return base_dir / relative_path


class DocsHTMLExtractor(HTMLParser):
    BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "header",
        "main",
        "table",
        "tr",
        "blockquote",
    }
    HEADING_LEVELS = {
        "h1": 1,
        "h2": 2,
        "h3": 3,
        "h4": 4,
        "h5": 5,
        "h6": 6,
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.current: list[str] = []
        self.list_depth = 0
        self.in_li = False
        self.in_pre = False
        self.in_code = False
        self.ignore_depth = 0
        self.heading_level: int | None = None
        self.seen_main = False
        self.main_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.ignore_depth += 1
            return
        if tag == "main":
            self.seen_main = True
            self.main_depth += 1
        if self.ignore_depth:
            return
        if tag in self.HEADING_LEVELS:
            self.flush_current()
            self.heading_level = self.HEADING_LEVELS[tag]
        elif tag in {"ul", "ol"}:
            self.flush_current()
            self.list_depth += 1
        elif tag == "li":
            self.flush_current()
            self.in_li = True
        elif tag == "pre":
            self.flush_current()
            self.parts.append("```")
            self.in_pre = True
        elif tag == "code" and not self.in_pre:
            self.current.append("`")
            self.in_code = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            if self.ignore_depth:
                self.ignore_depth -= 1
            return
        if tag == "main" and self.main_depth:
            self.main_depth -= 1
        if self.ignore_depth:
            return
        if tag in self.HEADING_LEVELS:
            self.flush_current()
            self.heading_level = None
        elif tag in {"ul", "ol"}:
            self.flush_current()
            self.list_depth = max(0, self.list_depth - 1)
        elif tag == "li":
            self.flush_current()
            self.in_li = False
        elif tag == "pre":
            self.flush_current()
            self.parts.append("```")
            self.in_pre = False
        elif tag == "code" and not self.in_pre and self.in_code:
            self.current.append("`")
            self.in_code = False
        elif tag in self.BLOCK_TAGS:
            self.flush_current()

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        if self.seen_main and self.main_depth <= 0:
            return
        text = unescape(data)
        if not text.strip():
            if self.in_pre:
                self.current.append(text)
            return
        self.current.append(text)

    def flush_current(self) -> None:
        if not self.current:
            return
        text = "".join(self.current)
        self.current = []
        if self.in_pre:
            self.parts.append(text.rstrip("\n"))
            return
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return
        if cleaned in {"Skip to main content", "Ask AI", "Copy"}:
            return
        if self.heading_level is not None:
            self.parts.append(f"{'#' * self.heading_level} {cleaned}")
            return
        if self.in_li:
            indent = "  " * max(0, self.list_depth - 1)
            self.parts.append(f"{indent}- {cleaned}")
            return
        self.parts.append(cleaned)

    def get_text(self) -> str:
        self.flush_current()
        lines: list[str] = []
        previous_blank = False
        for part in self.parts:
            stripped = part.strip()
            if not stripped:
                if previous_blank:
                    continue
                lines.append("")
                previous_blank = True
                continue
            if lines and not lines[-1]:
                pass
            elif lines:
                lines.append("")
            lines.append(stripped)
            previous_blank = False
        return "\n".join(lines).strip() + "\n"


def convert_html_to_markdownish(html: str) -> str:
    parser = DocsHTMLExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def fetch_url(url: str, timeout_s: int) -> tuple[bytes, dict[str, str]]:
    req = Request(
        url,
        headers={
            "User-Agent": "cambc-doc-sync/1.0",
            "Accept": "text/html, text/plain, text/markdown;q=0.9, */*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout_s) as response:
        body = response.read()
        headers = {k.lower(): v for k, v in response.headers.items()}
        headers["final_url"] = response.geturl()
        headers["status"] = str(response.status)
        return body, headers


def render_snapshot(entry: DocEntry, body: bytes, headers: dict[str, str]) -> tuple[str, str]:
    content_type = headers.get("content-type", "")
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    text = body.decode(charset, errors="replace")
    snapshot_kind = "raw-text"
    if "<html" in text.lower() or "text/html" in content_type:
        text = convert_html_to_markdownish(text)
        snapshot_kind = "html-extracted"
    sha256 = hashlib.sha256(body).hexdigest()
    header = "\n".join(
        [
            "---",
            f"title: {entry.title}",
            f"source_url: {entry.url}",
            f"final_url: {headers.get('final_url', entry.url)}",
            f"fetched_at_utc: {utc_now()}",
            f"content_type: {content_type or 'unknown'}",
            f"snapshot_kind: {snapshot_kind}",
            f"sha256: {sha256}",
            "warning: Pinned local snapshot. Re-check the live docs when freshness matters.",
            "---",
            "",
            f"# {entry.title}",
            "",
            f"Source: {entry.url}",
            "",
            f"Description: {entry.description}",
            "",
        ]
    )
    return header + text, sha256


def write_snapshot(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_manifest(records: Iterable[dict[str, str]]) -> str:
    payload = {
        "generated_at_utc": utc_now(),
        "warning": "Pinned local snapshots. Live docs remain authoritative when freshness matters.",
        "records": list(records),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync official Battlecode docs referenced by llms.txt into local pinned snapshots.")
    parser.add_argument("--llms", default=str(DEFAULT_LLM_PATH), help="Path to llms.txt")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write local snapshots into")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="List planned downloads without fetching")
    parser.add_argument("--force", action="store_true", help="Refresh even if the destination file already exists")
    parser.add_argument("--title-filter", help="Only sync docs whose title contains this case-insensitive substring")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    llms_path = Path(args.llms)
    output_dir = Path(args.output_dir)
    entries = parse_llms(llms_path)
    if args.title_filter:
        needle = args.title_filter.lower()
        entries = [entry for entry in entries if needle in entry.title.lower()]
    if not entries:
        raise SystemExit("No documentation entries selected")

    if args.dry_run:
        for entry in entries:
            print(f"{entry.title}: {entry.url} -> {output_path_for(output_dir, entry)}")
        return 0

    manifest_records: list[dict[str, str]] = []
    for entry in entries:
        destination = output_path_for(output_dir, entry)
        if destination.exists() and not args.force:
            print(f"skip {entry.title}: {destination}")
            manifest_records.append(
                {
                    "title": entry.title,
                    "source_url": entry.url,
                    "path": str(destination),
                    "status": "skipped_existing",
                }
            )
            continue

        print(f"fetch {entry.title}: {entry.url}")
        body, headers = fetch_url(entry.url, args.timeout)
        rendered, sha256 = render_snapshot(entry, body, headers)
        write_snapshot(destination, rendered)
        manifest_records.append(
            {
                "title": entry.title,
                "source_url": entry.url,
                "final_url": headers.get("final_url", entry.url),
                "path": str(destination),
                "content_type": headers.get("content-type", "unknown"),
                "status": "fetched",
                "sha256": sha256,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(build_manifest(manifest_records), encoding="utf-8")
    print(f"wrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
