"""pdf_parser.py

Module for extracting text from research paper PDFs, identifying numbered and unnumbered
sections/subsections using regex, preserving section hierarchy, and saving the output
as structured JSON.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

COMMON_HEADINGS = {
    'abstract', 'introduction', 'related work', 'related works', 'background',
    'methodology', 'methods', 'proposed method', 'proposed framework',
    'system model', 'architecture', 'experimental setup', 'experiments',
    'results', 'evaluation', 'discussion', 'conclusion', 'conclusions',
    'future work', 'references', 'acknowledgements', 'acknowledgments',
    'impact statement', 'theoretical guarantee', 'theoretical analysis'
}

# Prefix regex to identify image/figure/table captions
CAPTION_PREFIX_REGEX = re.compile(
    r'^\s*(?:Figure|Fig\.|Fig|Table|Tab\.|Tab|Algorithm|Listing|Chart|Scheme|Plate)\s*\d+.*',
    re.IGNORECASE
)

# Header/Footer/Page number patterns to ignore
HEADER_FOOTER_PATTERNS = [
    re.compile(r'^\s*\d{1,3}\s*$'),  # Standalone page number
    re.compile(r'^\s*Proceedings of the.*$', re.IGNORECASE),
    re.compile(r'^\s*Copyright \d{4}.*$', re.IGNORECASE),
    re.compile(r'^\s*Correspondence to:.*$', re.IGNORECASE),
    re.compile(r'^\s*\*\s*Equal contribution.*$', re.IGNORECASE),
]

# Diagram label patterns extracted from embedded graphics
DIAGRAM_LABEL_REGEX = re.compile(
    r'^\s*(?:Unlabel|Labeled)\s+Data\s*$|'
    r'^\s*(?:Student|Teacher)\s+Model.*$|'
    r'^\s*Model\s+[A-Z]\s*$|'
    r'^\s*(?:Local|Global)\s+Embedding\s*$|'
    r'^\s*Pseudo\s+Label\s*$|'
    r'^\s*(?:Frozen|Training)\s+Model\s*$|'
    r'^\s*MLP\([^)]*\)\s*$|'
    r'^\s*(?:Knowledge|Fusion)\s*$|'
    r'^\s*(?:Weak|Strong)\s+Aug\..*$|'
    r'^\s*Aug\.\s+[\d\s]+\s*$|'
    r'^\s*(?:Teacher|Student|Model)\s*$|'
    r'^\s*\d+[\d\s]+\d+\s*$',
    re.IGNORECASE
)

# Author & Affiliation detection patterns to filter out from preamble
AUTHOR_LINE_PATTERNS = [
    re.compile(r'^\s*Contributing authors?:', re.IGNORECASE),
    re.compile(r'^\s*Correspondenc[e|ing]', re.IGNORECASE),
    re.compile(r'^\s*\*\s*Equal contribution', re.IGNORECASE),
    re.compile(r'@[a-zA-Z0-9.\-_]+\.[a-zA-Z]{2,}'),  # Email addresses
    re.compile(r'\b(?:University|Department|Laboratory|Lab|Institute|School|Faculty|Center|Centre|Academy|Hospital)\b', re.IGNORECASE),
    re.compile(r'^\d\s*(?:[A-Z]|Department|University|Laboratory|Lab|Institute|School|Faculty)'),  # e.g. "1Shanghai AI Lab", "2Department"
    re.compile(r'\b(?:Shanghai|Beijing|Warwick|CUHK|Emory|Peking|Wuhan|Coventry|Hong Kong|China|USA|UK)\b', re.IGNORECASE),
]

# Multi-level numbered sections: e.g. 1.1 Background, 1.2.1 Motivation, Section 2.1 Overview
MULTI_LEVEL_REGEX = re.compile(
    r'^\s*(?:[Ss]ection\s+)?(?P<number>(?:\d+|[A-Z])(?:\.\d+)+)\.?(?:\s+|-)(?P<title>[A-Za-z0-9\s\-_:\(\)]+?)(?:\.|\s{2,}|\n|$)(?P<rest>.*)',
    re.IGNORECASE
)

# Single-level numbered sections: e.g. 1. Introduction, II. Related Work
SINGLE_LEVEL_REGEX = re.compile(
    r'^\s*(?:[Ss]ection\s+)?(?P<number>[IVXLCDM]+|\d+)\.?(?:\s+|-)(?P<title>[A-Za-z0-9\s\-_:\(\)]+?)(?:\.|\s{2,}|\n|$)(?P<rest>.*)',
    re.IGNORECASE
)


def extract_text_from_pdf(pdf_path: Union[str, Path]) -> str:
    """Extract full text from a PDF file using pypdf.

    Args:
        pdf_path: Path to the research paper PDF file.

    Returns:
        Extracted text content from the PDF as a string.

    Raises:
        ImportError: If pypdf is not installed.
        FileNotFoundError: If pdf_path does not exist.
    """
    if PdfReader is None:
        raise ImportError("The 'pypdf' package is required. Install it using 'pip install pypdf'.")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    reader = PdfReader(pdf_path)
    text_pages = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_pages.append(page_text)

    return "\n".join(text_pages)


def _clean_content_text(text: str) -> str:
    """Fixes words split across line breaks with hyphens (e.g. 'gen-\\neration' -> 'generation')
    and joins lines within paragraphs.
    """
    if not text:
        return ""

    # 1. Join words cut off across line breaks with hyphens
    # e.g., "pseudo-label gen-\neration" -> "pseudo-label generation"
    text = re.sub(r'([a-zA-Z]+)-\n\s*([a-zA-Z]+)', r'\1\2', text)
    text = re.sub(r'([a-zA-Z]+)-\n\s*([A-Z0-9]+)', r'\1-\2', text)

    # 2. Join lines within paragraphs while preserving double-newline paragraph breaks
    paragraphs = text.split('\n\n')
    cleaned_paragraphs = []

    for p in paragraphs:
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        if lines:
            paragraph_text = ' '.join(lines)
            paragraph_text = re.sub(r'[ \t]+', ' ', paragraph_text)
            cleaned_paragraphs.append(paragraph_text)

    return '\n\n'.join(cleaned_paragraphs)


def _is_author_or_affiliation_line(line: str) -> bool:
    """Returns True if a preamble line is an author name, affiliation, address, or email line."""
    s = line.strip()
    if not s:
        return False

    if any(pat.search(s) for pat in AUTHOR_LINE_PATTERNS):
        return True

    has_superscripts = bool(re.search(r'\b[A-Z][a-z]+\s*(?:\*\s*)?\d', s))
    has_multiple_names = len(re.findall(r'\b[A-Z][a-z]+\b', s)) >= 2
    if has_superscripts and has_multiple_names:
        return True

    return False


def _clean_preamble_lines(lines: List[str]) -> str:
    """Extracts paper title from preamble lines while dropping author names, affiliations,
    and email addresses.
    """
    title_lines = []
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        if _is_author_or_affiliation_line(raw):
            break
        title_lines.append(raw)

    clean_title_text = " ".join(title_lines).strip()
    return _clean_content_text(clean_title_text)


def _is_image_or_noise_line(line: str) -> bool:
    """Returns True if the line is extracted from an image, diagram label, figure/table caption,
    or page header/footer.
    """
    s = line.strip()
    if not s:
        return False

    # 1. Page numbers / running headers / conference footers
    if any(pat.match(s) for pat in HEADER_FOOTER_PATTERNS):
        return True

    # 2. Figure / Table / Algorithm captions
    if CAPTION_PREFIX_REGEX.match(s):
        return True

    # 3. Known diagram text labels
    if DIAGRAM_LABEL_REGEX.match(s):
        return True

    # 4. Pure numeric diagram string without math symbols (e.g. "0 0 1 40 1 1 0", "1 2 3 41 0 2 4")
    if not any(c.isalpha() for c in s):
        math_operators = {'=', '+', '×', '÷', '<', '>', '≤', '≥', '±', '≠', '∈', '∑', '∏', '∫'}
        if not any(op in s for op in math_operators):
            tokens = s.split()
            if len(tokens) >= 2 and all(t.isdigit() for t in tokens):
                return True

    return False


def _is_valid_heading(
    title: str,
    rest: str,
    is_single_num: bool = False,
    raw_line: str = "",
    number: Optional[str] = None
) -> bool:
    """Validates whether matched title text is genuinely a section heading rather than a body sentence,
    image label, or figure/table caption.
    """
    title_clean = title.strip()
    if not title_clean:
        return False

    # 1. Reject figure, table, algorithm, or image captions
    if CAPTION_PREFIX_REGEX.match(raw_line) or CAPTION_PREFIX_REGEX.match(title_clean):
        return False

    # 2. Must contain words starting with alphabetic characters
    alpha_words = [w for w in title_clean.split() if any(c.isalpha() for c in w)]
    if not alpha_words:
        return False

    # 3. Check section number validity (e.g. section number '0' is invalid for single-level unless in common headings)
    if is_single_num and number == '0' and title_clean.lower() not in COMMON_HEADINGS:
        return False

    # 4. Length limits on heading titles (words/characters)
    if len(alpha_words) > 10 or len(title_clean) > 80:
        return False

    rest_clean = rest.strip()
    if rest_clean:
        if len(alpha_words) > 6:
            return False
        first_alpha_char = next((c for c in title_clean if c.isalpha()), None)
        if first_alpha_char and not first_alpha_char.isupper():
            return False

    # 5. For single-level numbered sections (e.g. "1. Introduction"), enforce Title Case, ALL CAPS, or known heading
    if is_single_num:
        is_known = title_clean.lower() in COMMON_HEADINGS
        is_title_cased = all(
            w[0].isupper() for w in alpha_words if w and w[0].isalpha()
        )
        is_upper = title_clean.isupper()
        if not (is_known or is_title_cased or is_upper):
            return False

    return True


def identify_sections(text: str) -> List[Dict[str, Any]]:
    """Identifies numbered sections, subsections, and standard unnumbered sections from extracted text.
    Filters out image labels, figure/table captions, running headers/footers, and author metadata.

    Args:
        text: Plain text extracted from research paper.

    Returns:
        List of flat section dictionaries containing title, number, level, and content.
    """
    lines = text.splitlines()
    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None
    in_caption_block = False

    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            in_caption_block = False
            if current_section and current_section.get('content_lines') is not None:
                current_section['content_lines'].append('')
            continue

        matched_header = False
        number = None
        title = None
        level = 1
        rest_text = ""

        # Check section headings FIRST so valid section headings are never swallowed by captions
        # 1. Multi-level numbered sections (e.g. 1.1 Background, 1.2.1 Motivation)
        m_multi = MULTI_LEVEL_REGEX.match(raw_line)
        if m_multi:
            t = m_multi.group('title')
            r = m_multi.group('rest')
            num = m_multi.group('number')
            if _is_valid_heading(t, r, is_single_num=False, raw_line=raw_line, number=num):
                number = num
                title = t.strip()
                level = number.count('.') + 1
                rest_text = r.strip()
                matched_header = True

        # 2. Single-level numbered sections (e.g. 1. Introduction, II. Related Work)
        if not matched_header:
            m_single = SINGLE_LEVEL_REGEX.match(raw_line)
            if m_single:
                t = m_single.group('title')
                r = m_single.group('rest')
                num = m_single.group('number')
                if _is_valid_heading(t, r, is_single_num=True, raw_line=raw_line, number=num):
                    number = num
                    title = t.strip()
                    level = 1
                    rest_text = r.strip()
                    matched_header = True

        # 3. Common unnumbered section headings (e.g. Abstract, Introduction, References)
        if not matched_header and raw_line.lower() in COMMON_HEADINGS:
            number = None
            title = raw_line
            level = 1
            matched_header = True

        if matched_header:
            in_caption_block = False
            if current_section:
                if current_section.get('title') == 'Preamble':
                    current_section['content'] = _clean_preamble_lines(current_section.get('content_lines', []))
                else:
                    raw_content = "\n".join(current_section.get('content_lines', []))
                    current_section['content'] = _clean_content_text(raw_content)
                current_section.pop('content_lines', None)
                sections.append(current_section)

            content_lines = [rest_text] if rest_text else []
            current_section = {
                'title': title,
                'number': number,
                'level': level,
                'content_lines': content_lines
            }
            continue

        # Filter out figure/table captions (and their block continuations), diagram labels, page numbers & headers
        if CAPTION_PREFIX_REGEX.match(raw_line):
            in_caption_block = True
            continue

        if in_caption_block:
            if raw_line.endswith('.') and len(raw_line) > 30:
                in_caption_block = False
            continue

        if _is_image_or_noise_line(raw_line):
            continue

        if current_section:
            current_section['content_lines'].append(raw_line)
        else:
            # Text preceding the first section header (e.g. Paper Title)
            current_section = {
                'title': 'Preamble',
                'number': None,
                'level': 1,
                'content_lines': [raw_line]
            }

    if current_section:
        if current_section.get('title') == 'Preamble':
            current_section['content'] = _clean_preamble_lines(current_section.get('content_lines', []))
        else:
            raw_content = "\n".join(current_section.get('content_lines', []))
            current_section['content'] = _clean_content_text(raw_content)
        current_section.pop('content_lines', None)
        sections.append(current_section)

    return sections


def build_hierarchy(flat_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converts a flat list of section dictionaries into a nested tree structure based on section levels.

    Args:
        flat_sections: Flat list of section dicts (with keys: title, number, level, content).

    Returns:
        Nested list of top-level section dicts, each containing a 'subsections' list.
    """
    root_sections: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []

    for section in flat_sections:
        node = {
            'title': section['title'],
            'number': section.get('number'),
            'content': section.get('content', ''),
            'subsections': []
        }
        level = section.get('level', 1)

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            parent = stack[-1][1]
            parent['subsections'].append(node)
        else:
            root_sections.append(node)

        stack.append((level, node))

    return root_sections


def save_to_json(data: Union[List[Dict[str, Any]], Dict[str, Any]], output_path: Union[str, Path], indent: int = 2) -> None:
    """Saves structured section data to a JSON file.

    Args:
        data: Structured section hierarchy data.
        output_path: Target JSON file path.
        indent: Indentation level for JSON formatting.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def parse_pdf_to_json(pdf_path: Union[str, Path], output_json_path: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """High-level function to parse a research-paper PDF, extract text, identify section hierarchy,
    and optionally save the result as structured JSON.

    Args:
        pdf_path: Path to the input PDF file.
        output_json_path: Optional path to save the structured JSON.

    Returns:
        Structured list of top-level sections with nested subsections.
    """
    text = extract_text_from_pdf(pdf_path)
    flat_sections = identify_sections(text)
    hierarchy = build_hierarchy(flat_sections)

    if output_json_path:
        save_to_json(hierarchy, output_json_path)

    return hierarchy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse research-paper PDF into structured hierarchical JSON.")
    parser.add_argument("pdf_path", help="Path to input PDF file")
    parser.add_argument("-o", "--output", help="Path to output JSON file", default=None)

    args = parser.parse_args()
    out_path = args.output or Path(args.pdf_path).with_suffix(".json")
    result = parse_pdf_to_json(args.pdf_path, out_path)
    print(f"Successfully parsed '{args.pdf_path}' and saved structured JSON to '{out_path}' ({len(result)} top-level sections).")
