# Copyright 2026 Human Systems. MIT License.
"""Corpus retrieval helper for Switchboard agents.

Thin wrapper over `data.corpus` that exposes a result-oriented API suitable
for plugging into agent prompts. Keeps the data layer as the single source
of truth -- this module does no file I/O itself.

Public API:
    retrieve(query, top_k=5, ...)  -> list[RetrievedItem]
    format_for_prompt(items)       -> str
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from switchboard.env import ECOSYSTEM_ROOT as _ECOSYSTEM_ROOT

_raw_corpus_root = os.environ.get("CORPUS_ROOT", str(_ECOSYSTEM_ROOT))
_corpus_root_path = Path(_raw_corpus_root).resolve()
_allowed_root = _ECOSYSTEM_ROOT.resolve()
if _corpus_root_path.is_relative_to(_allowed_root) and str(_corpus_root_path) not in sys.path:
    sys.path.insert(0, str(_corpus_root_path))
_CORPUS_ROOT = _corpus_root_path

from data import corpus as corpus_api  # noqa: E402


@dataclass(frozen=True)
class RetrievedItem:
    """Single retrieval hit from the unified corpus."""

    identifier: str
    title: str
    source: str
    year: Optional[int]
    downloads: Optional[int]
    dl_per_year_alive: Optional[float]
    is_gem: bool
    topic: Optional[str]
    url: Optional[str]
    content_warning: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "source": self.source,
            "year": self.year,
            "downloads": self.downloads,
            "dl_per_year_alive": self.dl_per_year_alive,
            "is_gem": self.is_gem,
            "topic": self.topic,
            "url": self.url,
            "content_warning": self.content_warning,
        }


def _coerce_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def retrieve(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
    gem_only: bool = False,
    include_excluded: bool = False,
) -> list[RetrievedItem]:
    """Return up to `top_k` items matching `query` from the unified corpus.

    Policy-excluded rows are filtered out by default; pass
    `include_excluded=True` for auditing / reporting use-cases.
    """
    hits = corpus_api.search(
        query=query,
        top_k=top_k,
        source=source,
        gem_only=gem_only,
        retrievable_only=not include_excluded,
    )
    items: list[RetrievedItem] = []
    for rec in hits.to_dict(orient="records"):
        warn = rec.get("content_warning")
        try:
            import pandas as pd
            warn = None if warn is None or (isinstance(warn, float) and pd.isna(warn)) else str(warn)
        except Exception:
            warn = None if warn is None else str(warn)
        items.append(
            RetrievedItem(
                identifier=str(rec.get("identifier") or ""),
                title=str(rec.get("title") or ""),
                source=str(rec.get("source") or ""),
                year=_coerce_int(rec.get("year")),
                downloads=_coerce_int(rec.get("downloads")),
                dl_per_year_alive=_coerce_float(rec.get("dl_per_year_alive")),
                is_gem=bool(rec.get("is_gem")),
                topic=(rec.get("topic") or None),
                url=(rec.get("url") or None),
                content_warning=warn,
            )
        )
    return items


def format_for_prompt(items: list[RetrievedItem]) -> str:
    """Render hits as a compact markdown block for inclusion in an agent prompt.

    Any item with a `content_warning` is surfaced as a warning line below the
    table so the agent sees it before citing the item.
    """
    if not items:
        return "_(no matching items in corpus)_"
    lines = ["| # | Title | Source | Year | dl/yr | Gem | ⚠ |",
             "|--:|---|---|--:|--:|:-:|:-:|"]
    warnings: list[str] = []
    for i, it in enumerate(items, 1):
        title = (it.title or "")[:70].replace("|", "/")
        yr = it.year if it.year is not None else ""
        vel = f"{it.dl_per_year_alive:.1f}" if it.dl_per_year_alive is not None else ""
        gem = "★" if it.is_gem else ""
        warn_mark = "⚠" if it.content_warning else ""
        lines.append(f"| {i} | {title} | {it.source} | {yr} | {vel} | {gem} | {warn_mark} |")
        if it.content_warning:
            warnings.append(f"- **#{i} ({it.identifier})**: {it.content_warning}")
    if warnings:
        lines.append("")
        lines.append("**Content warnings:**")
        lines.extend(warnings)
    return "\n".join(lines)


def manifest_summary() -> dict:
    """Short manifest snapshot (row count, sources, gem count)."""
    m = corpus_api.load_manifest()
    return {
        "n_rows": m.get("n_rows"),
        "sources": m.get("rows_by_source"),
        "gem_flags_total": m.get("gem_flags_total"),
        "ref_year": m.get("ref_year"),
    }


__all__ = ["RetrievedItem", "retrieve", "format_for_prompt", "manifest_summary"]
