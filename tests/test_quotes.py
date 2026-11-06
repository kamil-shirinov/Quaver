from pathlib import Path

import pytest
import yaml

from quaver.quotes import (
    QuoteCheck,
    QuoteFailure,
    check_quotes,
    load_pages,
    quote_on_page,
    split_pages,
)
from quaver.spec import StrategySpec, load_spec

TEMPLATE = Path(__file__).parent.parent / "specs" / "TEMPLATE.yaml"
FIXTURE = Path(__file__).parent / "fixtures" / "example-paper.txt"


# --- split_pages ----------------------------------------------------------------------------


def test_split_pages() -> None:
    pages = split_pages("ignored preamble\n=== page 1 ===\nfirst\n=== page 2 ===\nsecond\n")
    assert pages == {1: "\nfirst\n", 2: "\nsecond\n"}


def test_split_pages_marker_must_be_whole_line() -> None:
    pages = split_pages("=== page 1 ===\nsee === page 2 === inline\n")
    assert list(pages) == [1]


def test_split_pages_tolerates_trailing_spaces_on_marker() -> None:
    assert list(split_pages("=== page 3 ===  \ntext\n")) == [3]


def test_split_pages_no_markers() -> None:
    with pytest.raises(ValueError, match="no '=== page N ===' markers found"):
        split_pages("just text\n")


def test_split_pages_duplicate_page() -> None:
    with pytest.raises(ValueError, match="page 2 appears more than once"):
        split_pages("=== page 2 ===\na\n=== page 2 ===\nb\n")


def test_load_pages_fixture() -> None:
    assert sorted(load_pages(FIXTURE)) == [1, 2, 3, 4, 5, 6, 7]


# --- quote_on_page: what is ignored ---------------------------------------------------------


@pytest.mark.parametrize(
    ("quote", "page"),
    [
        ("exact words here", "some exact words here."),
        ("words across lines", "words\nacross   \n   lines"),
        ("tabs  and   spaces", "tabs\tand spaces"),
        ("  padded quote  ", "a padded quote"),
        ("line\nbreak in quote", "line break in quote"),
        ("recommended reading", "recom-\nmended reading"),  # soft hyphen at line end
        ("recommended reading", "recom-  \n   mended reading"),
        ("T-Bills held", "in T-\nBills held"),  # real hyphen at line end
        ("T- Bills held", "in T-\nBills held"),
        ("two soft hyphens", "two so-\nft hy-\nphens"),
        ("ends at the hyph", "ends at the hyph-\nen"),
    ],
)
def test_quote_found(quote: str, page: str) -> None:
    assert quote_on_page(quote, page)


# --- quote_on_page: everything else counts --------------------------------------------------


@pytest.mark.parametrize(
    ("quote", "page"),
    [
        ("Exact words", "exact words"),  # case
        ("exact words.", "exact words"),  # punctuation
        ('"exact" words', "“exact” words"),  # quotation marks
        ("exactwords", "exact words"),  # whitespace may vary, not vanish
        ("exact words", "exactwords"),
        ("re-commended", "recommended"),  # hyphens away from line ends count
        ("recommended", "re-commended"),
        ("recommended", "re- commended"),  # line-end only: a hyphen before a space is real
        ("a b", "a -\nb"),  # a dash standing alone at the end of a line is not hyphenation
        ("1.10 percent", "1.1 percent"),
        ("missing", ""),
        ("", "any page"),  # an empty quote is never found
        ("   ", "any page"),
    ],
)
def test_quote_not_found(quote: str, page: str) -> None:
    assert not quote_on_page(quote, page)


# --- check_quotes ---------------------------------------------------------------------------


def test_check_quotes_template_against_fixture() -> None:
    assert check_quotes(load_spec(TEMPLATE), load_pages(FIXTURE)) == QuoteCheck(11, 1, [])


def test_check_quotes_reports_failures_in_file_order() -> None:
    pages = load_pages(FIXTURE)
    del pages[3]
    result = check_quotes(load_spec(TEMPLATE), pages)
    failures = result.failures
    assert (result.checked, result.skipped) == (11, 1)
    assert [(f.where, f.page) for f in failures] == [
        ("universe", 3),
        ("data_source", 3),
        ("sample_start", 3),
        ("sample_end", 3),
    ]
    assert failures[0] == QuoteFailure(
        "universe", 3, "We use all common stocks listed on the Example Exchange."
    )


def test_check_quotes_skips_table_sources() -> None:
    spec = load_spec(TEMPLATE)
    # The table claim's page is not even in the text, and it is still not a failure.
    pages = {page: text for page, text in load_pages(FIXTURE).items() if page != 7}
    result = check_quotes(spec, pages)
    assert result.skipped == 1
    assert all(f.where != "C3" for f in result.failures)


def test_check_quotes_checks_metric_definitions() -> None:
    data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    data["metrics"]["mean_monthly_return"]["source"] = {
        "kind": "stated",
        "page": 7,
        "quote": "This sentence is not on the page.",
    }
    result = check_quotes(StrategySpec.model_validate(data), load_pages(FIXTURE))
    assert (result.checked, result.skipped) == (12, 1)
    assert [f.where for f in result.failures] == ["metrics.mean_monthly_return"]
