"""The six tools, exactly as named in the design document."""

from tools.build_table import build_rows, compare_paragraph, worst_level
from tools.extract_claims import extract_claims
from tools.fetch_pdf import fetch_pdf
from tools.parse_sections import parse_sections, split_sections
from tools.search_papers import search_papers
from tools.verify_citation import ccr, normalize, verify_citation

TOOL_NAMES = [
    "search_papers",
    "fetch_pdf",
    "parse_sections",
    "extract_claims",
    "build_table",
    "verify_citation",
]

__all__ = [
    "search_papers",
    "fetch_pdf",
    "parse_sections",
    "extract_claims",
    "build_rows",
    "compare_paragraph",
    "verify_citation",
    "ccr",
    "normalize",
    "split_sections",
    "worst_level",
    "TOOL_NAMES",
]
