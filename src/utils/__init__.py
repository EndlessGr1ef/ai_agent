"""Utility functions and simple tool framework for LLM agents."""

import os
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Callable

from utils.token_counter import count_tokens_in_messages
from utils.reasoning import extract_reasoning_details
from utils.arg_parser import parse_args


# -----------------------------
# Minimal Tool Framework
# -----------------------------

@dataclass
class ToolResult:
    ok: bool
    message: str
    data: Optional[Any] = None


class Tool:
    name: str
    description: str

    def __init__(self, name: str, description: str, executor: Callable[[Dict[str, Any]], ToolResult]):
        self.name = name
        self.description = description
        self._executor = executor

    def execute(self, args: Dict[str, Any]) -> ToolResult:
        return self._executor(args)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, str]:
        return {name: t.description for name, t in self._tools.items()}


# -----------------------------
# Markdown File Operations
# -----------------------------

SAFE_DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'docs', 'project_documents')


def _normalize_md_path(path: str) -> str:
    """
    Normalize a relative markdown path under SAFE_DOCS_DIR.
    Disallow absolute paths or parent directory escapes.
    """
    path = path.strip()
    if not path.endswith('.md'):
        raise ValueError('Only .md files are allowed')
    if os.path.isabs(path):
        raise ValueError('Absolute paths are not allowed')
    if '..' in path.replace('\\', '/'):  # prevent escape
        raise ValueError('Path traversal is not allowed')
    final_dir = os.path.abspath(SAFE_DOCS_DIR)
    final_path = os.path.abspath(os.path.join(final_dir, path))
    if not final_path.startswith(final_dir):
        raise ValueError('Target path escapes safe directory')
    return final_path


def create_markdown_file(path: str, content: str, overwrite: bool = False) -> str:
    """
    Create a markdown file safely under SAFE_DOCS_DIR.

    Returns the absolute path written.
    """
    final_path = _normalize_md_path(path)
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    if os.path.exists(final_path) and not overwrite:
        raise FileExistsError(f'File already exists: {final_path}')
    with open(final_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return final_path


def build_markdown_create_tool() -> Tool:
    def _exec(args: Dict[str, Any]) -> ToolResult:
        try:
            path = args.get('path') or args.get('filename')
            content = args.get('content') or ''
            overwrite = bool(args.get('overwrite', False))
            if not path:
                return ToolResult(False, 'Missing required argument: path')
            written = create_markdown_file(path, content, overwrite)
            return ToolResult(True, f'Markdown written: {written}', {'path': written})
        except Exception as e:
            return ToolResult(False, f'Markdown create failed: {e}')

    return Tool(name='markdown_create', description='Create a markdown file under docs/project_documents', executor=_exec)


# -----------------------------
# Lightweight Web Search (adapter stub)
# -----------------------------

def _duckduckgo_html_search(query: str, limit: int = 5) -> Dict[str, Any]:
    """Very lightweight DuckDuckGo HTML search (best-effort)."""
    import urllib.parse
    import urllib.request

    q = urllib.parse.quote(query)
    url = f"https://duckduckgo.com/html/?q={q}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')

    # naive parse of results
    results = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        link = m.group(1)
        title = re.sub(r'<.*?>', '', m.group(2))
        results.append({'title': title.strip(), 'url': link})
        if len(results) >= limit:
            break
    return {'query': query, 'results': results}


def build_web_search_tool() -> Tool:
    def _exec(args: Dict[str, Any]) -> ToolResult:
        try:
            query = args.get('query')
            limit = int(args.get('limit', 5))
            if not query:
                return ToolResult(False, 'Missing required argument: query')
            data = _duckduckgo_html_search(query, limit)
            count = len(data.get('results', []))
            return ToolResult(True, f'Found {count} results for: {query}', data)
        except Exception as e:
            return ToolResult(False, f'Web search failed: {e}')

    return Tool(name='web_search', description='Search the web and return links and titles', executor=_exec)


__all__ = [
    'count_tokens_in_messages',
    'extract_reasoning_details',
    'parse_args',
    'Tool',
    'ToolResult',
    'ToolRegistry',
    'create_markdown_file',
    'build_markdown_create_tool',
    'build_web_search_tool',
]
