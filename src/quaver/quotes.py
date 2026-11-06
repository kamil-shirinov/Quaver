"""Check that every quote in a spec appears on the page it cites.

The paper text is a plain file with a ``=== page N ===`` line before each page. A quote matches
when it appears on its cited page, ignoring only differences in whitespace and hyphenation at
line ends: any run of whitespace matches any other run, and a hyphen at the end of a line may
be read as a soft hyphen (``recom-`` / ``mended`` = ``recommended``) or as a real one
(``T-`` / ``Bills`` = ``T-Bills`` or ``T- Bills``). Nothing else is ignored: case, punctuation
and quotation marks must match exactly.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from quaver.spec import Provenance, StrategySpec, sources

_PAGE_MARKER = re.compile(r"^=== page (\d+) ===[ \t]*$", re.MULTILINE)
# A hyphen right after a non-space character, then the end of the line, then any indentation.
_LINE_END_HYPHEN = re.compile(r"(?<=\S)-[^\S\n]*\n\s*")
_WHITESPACE = re.compile(r"\s+")
# Stands for a line-end hyphen in normalised page text. Never occurs in real text.
_HYPHEN = "\x00"


@dataclass(frozen=True)
class QuoteFailure:
    """A quote that was not found on the page its source cites."""

    where: str
    page: int | None
    quote: str


@dataclass(frozen=True)
class QuoteCheck:
    """The outcome of checking a spec: quotes checked, table values skipped, failures."""

    checked: int
    skipped: int
    failures: list[QuoteFailure]


def split_pages(text: str) -> dict[int, str]:
    """Split page-marked text into {page number: page text}."""
    parts = _PAGE_MARKER.split(text)
    if len(parts) == 1:
        raise ValueError("no '=== page N ===' markers found")
    pages: dict[int, str] = {}
    for number, body in zip(parts[1::2], parts[2::2], strict=True):
        page = int(number)
        if page in pages:
            raise ValueError(f"page {page} appears more than once")
        pages[page] = body
    return pages


def _normalise_page(text: str) -> str:
    return _WHITESPACE.sub(" ", _LINE_END_HYPHEN.sub(_HYPHEN, text))


def _normalise_quote(quote: str) -> str:
    return _WHITESPACE.sub(" ", quote).strip()


def _matches_at(page: str, i: int, quote: str, j: int) -> bool:
    while j < len(quote):
        if i == len(page):
            return False
        if page[i] == _HYPHEN:
            # Soft hyphen (consumes nothing), real hyphen, or real hyphen followed by a space.
            options = [j]
            if quote[j] == "-":
                options.append(j + 1)
                if quote[j + 1 : j + 2] == " ":
                    options.append(j + 2)
            return any(_matches_at(page, i + 1, quote, k) for k in options)
        if page[i] != quote[j]:
            return False
        i += 1
        j += 1
    return True


def quote_on_page(quote: str, page_text: str) -> bool:
    """Whether the quote appears in the page text, up to whitespace and line-end hyphens.

    An empty quote is never found: it would otherwise match every page.
    """
    page = _normalise_page(page_text)
    needle = _normalise_quote(quote)
    return bool(needle) and any(_matches_at(page, i, needle, 0) for i in range(len(page) + 1))


def check_quotes(spec: StrategySpec, pages: dict[int, str]) -> QuoteCheck:
    """Check every quoted source. Table sources have no quote and are counted as skipped."""
    checked = skipped = 0
    failures: list[QuoteFailure] = []
    for where, source in sources(spec):
        if source.kind is Provenance.TABLE:
            skipped += 1
            continue
        if source.quote is None:
            continue
        checked += 1
        # A quote without a page (allowed on an assumed source) cannot be checked, so it fails.
        if source.page is None or not quote_on_page(source.quote, pages.get(source.page, "")):
            failures.append(QuoteFailure(where, source.page, source.quote))
    return QuoteCheck(checked, skipped, failures)


def load_pages(path: Path) -> dict[int, str]:
    """Read a page-marked text file."""
    return split_pages(path.read_text(encoding="utf-8"))
