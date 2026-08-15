"""
src/app.py - Paper Lens Streamlit Web Application

A premium, dark-mode glass-morphism interface for Paper Lens.
Features:
- Glassmorphism CSS components (.glass-card, .glass-panel).
- Top Nav with Logo and API Health Status indicator.
- Hero/Upload Card with simulated real-time progress bar & hover-scaling accent gradient button.
- Data Tabs:
  1. Sections: Collapsible section tree with real-time search filtering.
  2. Glossary: Term accordion with Jargon Scores, Context/General definitions, & Copy buttons.
- Footer with muted gradient and hover-scaling links.
"""

import base64
import html
import json
import os
import sys
import time
from pathlib import Path
import urllib.request

import streamlit as st

# Anchor paths relative to src directory
_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
_OUTPUTS_DIR = _SRC_DIR / "outputs"
_DATA_DIR = _SRC_DIR / "data"
_LOGO_PATH = _SRC_DIR / "assets" / "logo.png"

# Add project root to path for imports
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Attempt imports of internal pipeline modules
try:
    from parser.pdf_parser import parse_pdf_to_json
    from agents.pipeline import run_pipeline
    PIPELINE_AVAILABLE = True
except Exception as e:
    PIPELINE_AVAILABLE = False
    PIPELINE_ERROR = str(e)


# ------------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & THEME SETUP
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Paper Lens — Agentic AI Paper Explainer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Initialize Session State
if "parsed_data" not in st.session_state:
    st.session_state.parsed_data = None
if "glossary_data" not in st.session_state:
    st.session_state.glossary_data = None
if "paper_title" not in st.session_state:
    st.session_state.paper_title = None
if "copied_terms" not in st.session_state:
    st.session_state.copied_terms = {}
if "processing" not in st.session_state:
    st.session_state.processing = False


def load_logo_base64() -> str:
    """Load logo as base64 string for direct inline HTML embedding."""
    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{encoded}"
    return ""


LOGO_BASE64 = load_logo_base64()

# ------------------------------------------------------------------------------
# 2. CUSTOM CSS (Glassmorphism, Typography, Animations)
# ------------------------------------------------------------------------------
def get_css() -> str:
    bg_color = "#0B0F17"
    card_bg = "rgba(22, 27, 38, 0.65)"
    panel_bg = "rgba(30, 37, 51, 0.5)"
    text_color = "#F3F4F6"
    muted_color = "#9CA3AF"
    border_color = "rgba(255, 255, 255, 0.08)"
    input_bg = "rgba(15, 23, 42, 0.6)"

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap');

    html, body, [class*="st-"], .stMarkdown {{
        font-family: 'Inter', sans-serif !important;
        color: {text_color};
    }}

    /* Don't let the global font override break Streamlit's ligature-based Material icons
       (expander arrows, uploader icon, etc.) — they render as raw text like
       "keyboard_arrow_down" if forced into a non-icon font. */
    [data-testid="stIconMaterial"],
    .material-icons {{
        font-family: 'Material Symbols Rounded' !important;
    }}

    .stApp {{
        background: {bg_color} !important;
        background-image: radial-gradient(at 0% 0%, rgba(79, 70, 229, 0.15) 0px, transparent 50%), radial-gradient(at 100% 100%, rgba(124, 58, 237, 0.15) 0px, transparent 50%) !important;
        background-attachment: fixed !important;
    }}

    /* Typography */
    h1, h2, h3, h4, h5, h6, .outfit-font {{
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700;
        letter-spacing: -0.02em;
    }}

    /* Glassmorphism Components */
    .glass-card {{
        background: {card_bg} !important;
        backdrop-filter: blur(16px) saturate(180%);
        -webkit-backdrop-filter: blur(16px) saturate(180%);
        border: 1px solid {border_color};
        border-radius: 20px;
        padding: 32px;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }}

    .glass-card:hover {{
        border-color: rgba(99, 102, 241, 0.4);
    }}

    .glass-panel {{
        background: {panel_bg} !important;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid {border_color};
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
        transition: all 0.25s ease;
    }}

    .glass-panel:hover {{
        box-shadow: 0 8px 24px rgba(79, 70, 229, 0.12);
    }}

    /* ── Section Tree ─────────────────────────────────── */
    .sec-card {{
        border-radius: 14px;
        padding: 18px 22px;
        margin-bottom: 10px;
        border: 1px solid {border_color};
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }}
    .sec-card:hover {{
        box-shadow: 0 6px 20px rgba(79, 70, 229, 0.12);
    }}
    .sec-card-l0 {{
        background: rgba(99, 102, 241, 0.07);
        border-left: 3px solid #6366F1;
    }}
    .sec-card-l1 {{
        background: rgba(168, 85, 247, 0.06);
        border-left: 3px solid #A855F7;
        margin-left: 18px;
    }}
    .sec-card-l2 {{
        background: rgba(30, 37, 51, 0.45);
        border-left: 3px solid rgba(148, 163, 184, 0.4);
        margin-left: 36px;
    }}
    .sec-title {{
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        font-size: 1.05rem;
        letter-spacing: -0.01em;
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 0;
    }}
    .sec-title-l0 {{
        font-size: 1.15rem;
        background: linear-gradient(135deg, #818CF8 0%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .sec-title-l1 {{
        color: #C4B5FD;
    }}
    .sec-title-l2 {{
        color: #94A3B8;
        font-size: 0.95rem;
        font-weight: 600;
    }}
    .sec-num {{
        font-family: 'Outfit', sans-serif;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        padding: 2px 8px;
        border-radius: 6px;
        background: rgba(99, 102, 241, 0.18);
        color: #818CF8;
        flex-shrink: 0;
    }}
    .sec-page {{
        font-size: 0.72rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 6px;
        background: rgba(148, 163, 184, 0.1);
        color: #64748B;
        flex-shrink: 0;
        margin-left: auto;
    }}
    .sec-body {{
        margin-top: 14px;
        color: #CBD5E1;
        font-size: 0.92rem;
        line-height: 1.75;
        font-family: 'Inter', sans-serif;
    }}
    .sec-body p {{
        margin: 0 0 10px 0;
    }}
    .sec-body p:last-child {{
        margin-bottom: 0;
    }}
    .sec-divider {{
        height: 1px;
        background: linear-gradient(90deg, rgba(99,102,241,0.3) 0%, transparent 100%);
        margin: 10px 0 14px;
    }}
    .sec-no-content {{
        color: #475569;
        font-style: italic;
        font-size: 0.85rem;
        margin-top: 10px;
    }}
    .sec-children {{
        margin-top: 10px;
    }}

    /* ── Jargon Highlight Pills ───────────────────── */
    .jargon-pill {{
        background: rgba(99, 102, 241, 0.18);
        color: #A5B4FC;
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 4px;
        padding: 1px 5px;
        font-weight: 600;
        font-size: 0.87em;
    }}

    /* Top Navigation Bar */
    .top-nav {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 28px;
        background: {card_bg};
        backdrop-filter: blur(20px);
        border: 1px solid {border_color};
        border-radius: 18px;
        margin-bottom: 28px;
    }}

    .brand-title {{
        font-family: 'Outfit', sans-serif;
        font-size: 1.6rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6366F1 0%, #A855F7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        display: inline-block;
        margin-left: 12px;
    }}

    /* Status Indicator */
    .status-badge {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 14px;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
        background: rgba(16, 185, 129, 0.12);
        color: #10B981;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .status-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #10B981;
        box-shadow: 0 0 10px #10B981;
        animation: pulse 2s infinite;
    }}

    @keyframes pulse {{
        0% {{ opacity: 1; transform: scale(1); }}
        50% {{ opacity: 0.5; transform: scale(1.2); }}
        100% {{ opacity: 1; transform: scale(1); }}
    }}

    /* Primary Accent Button Styling */
    .stButton > button {{
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 28px !important;
        font-family: 'Outfit', sans-serif !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        box-shadow: 0 8px 25px rgba(79, 70, 229, 0.35) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        width: 100%;
    }}

    .stButton > button:hover {{
        transform: scale(1.025) translateY(-2px) !important;
        box-shadow: 0 12px 30px rgba(124, 58, 237, 0.5) !important;
    }}

    /* Jargon Badge */
    .jargon-badge {{
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-left: 8px;
    }}

    .score-high {{
        background: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }}

    .score-mid {{
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .score-low {{
        background: rgba(59, 130, 246, 0.15);
        color: #60A5FA;
        border: 1px solid rgba(59, 130, 246, 0.3);
    }}

    /* Definition Cards */
    .def-box {{
        background: {input_bg};
        border-left: 3px solid #6366F1;
        border-radius: 8px;
        padding: 14px 18px;
        margin-top: 10px;
        margin-bottom: 14px;
    }}

    .def-title {{
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        color: #818CF8;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }}

    /* Footer */
    .footer-container {{
        margin-top: 60px;
        padding: 32px 24px;
        border-top: 1px solid {border_color};
        background: linear-gradient(180deg, transparent 0%, {card_bg} 100%);
        border-radius: 20px 20px 0 0;
        text-align: center;
    }}

    .footer-links {{
        display: flex;
        justify-content: center;
        gap: 16px;
        margin-top: 20px;
        flex-wrap: wrap;
    }}

    .footer-glass-btn {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 10px 22px;
        border-radius: 12px;
        font-size: 0.9rem;
        font-weight: 600;
        font-family: 'Outfit', sans-serif;
        color: #C4B5FD;
        text-decoration: none;
        background: rgba(99, 102, 241, 0.10);
        border: 1px solid rgba(99, 102, 241, 0.30);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.08);
    }}

    .footer-glass-btn:hover {{
        background: rgba(99, 102, 241, 0.22);
        border-color: rgba(99, 102, 241, 0.6);
        color: #E0E7FF;
        transform: translateY(-2px) scale(1.04);
        box-shadow: 0 8px 24px rgba(99, 102, 241, 0.25);
    }}

    /* Custom Streamlit Input Overrides */
    .stTextInput > div > div > input {{
        background: {input_bg} !important;
        color: {text_color} !important;
        border: 1px solid {border_color} !important;
        border-radius: 12px !important;
        padding: 10px 16px !important;
    }}

    .stTextInput > div > div > input:focus {{
        border-color: #6366F1 !important;
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.3) !important;
    }}

    /* Expander styling */
    .streamlit-expanderHeader {{
        font-family: 'Outfit', sans-serif !important;
        font-weight: 600 !important;
        background: {panel_bg} !important;
        border-radius: 10px !important;
        color: {text_color} !important;
    }}

    /* Progress bar */
    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, #4F46E5 0%, #7C3AED 50%, #EC4899 100%) !important;
        border-radius: 10px !important;
    }}

    /* Hide the native file-uploader's own "Drag and drop..." instructions —
       our custom hero panel above already explains what to upload, so both
       were rendering stacked on top of each other. */
    [data-testid="stFileUploaderDropzoneInstructions"] {{
        display: none !important;
    }}

    [data-testid="stFileUploader"] {{
        margin-top: 4px;
    }}

    [data-testid="stFileUploaderDropzone"] {{
        background: {input_bg} !important;
        border: 1px dashed {border_color} !important;
        border-radius: 12px !important;
        padding: 10px !important;
        min-height: unset !important;
    }}

    /* Fix Streamlit Header Overlap */
    header[data-testid="stHeader"], [data-testid="stHeader"] {{
        background: transparent !important;
        z-index: 10 !important;
    }}

    /* Container padding so top toolbar sits cleanly above logo and top nav */
    .block-container {{
        padding-top: 4.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1240px !important;
    }}
    </style>
    """




st.markdown(get_css(), unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# 3. HELPER DATA FUNCTIONS
# ------------------------------------------------------------------------------
def check_api_health() -> bool:
    """Check if local FastAPI server or pipeline is active."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/docs", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return PIPELINE_AVAILABLE



# ------------------------------------------------------------------------------
# 4. TOP NAVIGATION BAR
# ------------------------------------------------------------------------------
api_status = check_api_health()
status_label = "🟢 API Connected" if api_status else "🟡 Pipeline Mode Ready"

nav_col1, nav_col2 = st.columns([7, 4])

with nav_col1:
    logo_html = f'<img src="{LOGO_BASE64}" height="40" style="vertical-align: middle;">' if LOGO_BASE64 else '🔍'
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 14px;">
            {logo_html}
            <div>
                <span class="brand-title">Paper Lens</span>
                <span style="font-size: 0.85rem; color: #9CA3AF; margin-left: 10px; font-weight: 500;">
                    Agentic AI Research Paper Explainer
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with nav_col2:
    st.markdown(
        f"""
        <div style="text-align: right; margin-top: 6px;">
            <span class="status-badge">
                <span class="status-dot"></span>
                {status_label}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# 5. HERO / UPLOAD CARD SECTION
# ------------------------------------------------------------------------------
hero_col1, hero_col2 = st.columns([7, 5])

with hero_col1:
    st.markdown(
        """
        <h1 style="font-size: 2.4rem; margin-bottom: 8px; background: linear-gradient(135deg, #FFFFFF 0%, #A5B4FC 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            Understand Complex AI/ML Papers Instantly
        </h1>
        <p style="font-size: 1.05rem; line-height: 1.6; color: #9CA3AF; margin-bottom: 24px;">
            Upload any research paper PDF. Our sequential two-agent LLM pipeline extracts key domain-specific terminology, generates context-aware definitions, and presents structured paper sections.
        </p>
        """,
        unsafe_allow_html=True,
    )

with hero_col2:
    st.markdown(
        """
        <div class="glass-panel" style="text-align: center; border-color: rgba(99, 102, 241, 0.3);">
            <div style="font-size: 2rem; margin-bottom: 6px;">📄</div>
            <div style="font-weight: 700; font-family: 'Outfit'; font-size: 1.1rem; color: #818CF8;">
                Upload Research PDF
            </div>
            <div style="font-size: 0.82rem; color: #9CA3AF; margin-bottom: 12px;">
                Supports arXiv papers, Conference PDFs, & Custom reports
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

uploaded_file = st.file_uploader(
    "Drag & drop your PDF file here", type=["pdf"], key="pdf_uploader", label_visibility="collapsed"
)

process_btn = st.button("✨ Analyze Research Paper", key="process_pdf_btn")

# ------------------------------------------------------------------------------
# 6. PIPELINE EXECUTION & REAL-TIME PROGRESS
# ------------------------------------------------------------------------------
if process_btn:
    if uploaded_file is not None:
        st.session_state.processing = True
        progress_bar = st.progress(0)
        status_text = st.empty()

        temp_pdf_path = _DATA_DIR / uploaded_file.name
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(temp_pdf_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Real-time progress bar simulation
        status_text.markdown("⏳ **Step 1/3: Extracting text & parsing section hierarchy...**")
        progress_bar.progress(25)
        time.sleep(0.6)

        try:
            if PIPELINE_AVAILABLE:
                parsed_sections = parse_pdf_to_json(temp_pdf_path)

                # Persist raw parser output
                _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                parsed_out_path = _OUTPUTS_DIR / f"parsed_{temp_pdf_path.stem}.json"
                with open(parsed_out_path, "w", encoding="utf-8") as _f:
                    json.dump(parsed_sections, _f, indent=2, ensure_ascii=False)

                status_text.markdown("🧠 **Step 2/3: Agent 1 — Scanning domain terms & jargon scores...**")
                progress_bar.progress(55)
                time.sleep(0.5)

                status_text.markdown("📝 **Step 3/3: Agent 2 — Generating context & general definitions...**")
                progress_bar.progress(85)

                result = run_pipeline(parsed_sections, pdf_name=temp_pdf_path.stem)
                progress_bar.progress(100)
                time.sleep(0.4)
                
                status_text.empty()
                progress_bar.empty()

                st.session_state.paper_title = result.get("paper_title", temp_pdf_path.stem)
                st.session_state.parsed_data = parsed_sections
                st.session_state.glossary_data = result.get("glossary", [])
                st.toast("Pipeline completed successfully!", icon="✅")
            else:
                st.warning("LLM Pipeline dependencies unavailable. Loading parsed structured view.")
                parsed_sections = parse_pdf_to_json(temp_pdf_path)

                # Persist raw parser output
                _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
                parsed_out_path = _OUTPUTS_DIR / f"parsed_{temp_pdf_path.stem}.json"
                with open(parsed_out_path, "w", encoding="utf-8") as _f:
                    json.dump(parsed_sections, _f, indent=2, ensure_ascii=False)

                st.session_state.paper_title = temp_pdf_path.stem
                st.session_state.parsed_data = parsed_sections
                st.session_state.glossary_data = []
        except Exception as err:
            st.error(f"Processing error: {err}")
    else:
        st.info("Please upload a PDF file to analyze.")


st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# 7. DATA TABS SECTION (Radix UI Style)
# ------------------------------------------------------------------------------
st.markdown(
    f"""
    <div style="margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
        <div>
            <h2 style="font-size: 1.8rem; margin: 0; background: linear-gradient(135deg, #6366F1 0%, #A855F7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                {st.session_state.paper_title or "Paper Analysis"}
            </h2>
            <div style="font-size: 0.9rem; color: #9CA3AF; margin-top: 4px;">
                Structured Hierarchy ({len(st.session_state.parsed_data or [])} top-level sections) • {len(st.session_state.glossary_data or [])} Key Terms Extracted
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab1, tab2 = st.tabs([
    "📂 Sections Tree",
    "📚 AI/ML Glossary"
])

# ------------------------------------------------------------------------------
# TAB 1: SECTIONS TREE WITH LIVE SEARCH FILTER
# ------------------------------------------------------------------------------
with tab1:
    search_query = st.text_input(
        "Search Section",
        placeholder="🔍 Type keywords to filter section titles and content (e.g. 'Encoder', 'Loss', 'Masking')...",
        key="section_search_input",
        label_visibility="collapsed"
    )

    import re as _re

    def _clean_text(raw: str) -> str:
        """Fix common PDF extraction artifacts and reflow text into readable paragraphs."""
        if not raw:
            return ""
        # Fix common ligature / encoding artifacts
        text = raw
        text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
        text = text.replace("\ufb03", "ffi").replace("\ufb04", "ffl")
        text = text.replace("\u2019", "'").replace("\u2018", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2013", "\u2013").replace("\u2014", "\u2014")
        # Fix hyphenated line-breaks (word-\nbreak -> wordbreak)
        text = _re.sub(r'(\w)-\n(\w)', r'\1\2', text)
        # Collapse mid-word line breaks that aren't sentence endings
        text = _re.sub(r'(?<!\.)\n(?![\n\-\d•*])', ' ', text)
        # Normalise multiple blank lines -> paragraph break sentinel
        text = _re.sub(r'\n{2,}', '\n\n', text)
        # Collapse runs of spaces
        text = _re.sub(r'[ \t]{2,}', ' ', text)
        return text.strip()

    def _paragraphs_html(content: str, terms: list = None) -> str:
        """Clean text, optionally highlight jargon terms, wrap in <p> tags."""
        cleaned = _clean_text(content)
        if not cleaned:
            return ""

        # Build a single combined regex for all glossary terms (longest-first
        # so multi-word terms match before their short sub-strings).
        pattern = None
        if terms:
            sorted_terms = sorted(terms, key=lambda t: len(t.get('term', '')), reverse=True)
            pattern = _re.compile(
                '|'.join(_re.escape(t['term']) for t in sorted_terms),
                _re.IGNORECASE,
            )

        paras = [p.strip() for p in cleaned.split('\n\n') if p.strip()]
        parts = []
        for para in paras:
            if pattern:
                buf, last = [], 0
                for m in pattern.finditer(para):
                    buf.append(html.escape(para[last:m.start()]))
                    buf.append(f'<span class="jargon-pill">{html.escape(m.group(0))}</span>')
                    last = m.end()
                buf.append(html.escape(para[last:]))
                parts.append(f"<p>{''.join(buf)}</p>")
            else:
                parts.append(f'<p>{html.escape(para)}</p>')
        return ''.join(parts)

    def render_section(sec: dict, level: int = 0, terms: list = None):
        title   = sec.get("title", "Untitled Section")
        num     = sec.get("number")
        page    = sec.get("page_number")
        content = sec.get("content", "")
        subsections = sec.get("subsections", [])

        # ── Search filter ──────────────────────────────────────
        if search_query.strip():
            q = search_query.lower().strip()
            matches_title   = q in title.lower() or (num and q in str(num))
            matches_content = q in content.lower()
            matches_sub     = any(
                q in sub.get("title", "").lower() or q in sub.get("content", "").lower()
                for sub in subsections
            )
            if not (matches_title or matches_content or matches_sub):
                return

        # ── Depth styling ──────────────────────────────────────
        depth_cls = "l0" if level == 0 else ("l1" if level == 1 else "l2")

        num_badge  = f'<span class="sec-num">{num}</span>' if num else ""
        page_badge = f'<span class="sec-page">p.{page}</span>' if page else ""
        body_html  = _paragraphs_html(content, terms)
        body_block = (
            f'<div class="sec-divider"></div><div class="sec-body">{body_html}</div>'
            if body_html
            else '<div class="sec-no-content">No text content — section is a heading only.</div>'
        )

        expander_label = f"{num + '. ' if num else ''}{title}"
        with st.expander(expander_label, expanded=(level == 0 and bool(search_query))):
            card_html = (
                f'<div class="sec-card sec-card-{depth_cls}">'
                f'<div class="sec-title sec-title-{depth_cls}">'
                f'{num_badge}'
                f'<span>{html.escape(title)}</span>'
                f'{page_badge}'
                f'</div>'
                f'{body_block}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
            if subsections:
                for sub in subsections:
                    render_section(sub, level=level + 1, terms=terms)

    glossary_terms = st.session_state.glossary_data or []

    sections = st.session_state.parsed_data or []
    if sections:
        for sec in sections:
            render_section(sec, terms=glossary_terms)
    else:
        st.info("No section data available.")

# ------------------------------------------------------------------------------
# TAB 2: AI/ML GLOSSARY WITH COPY FUNCTIONALITY
# ------------------------------------------------------------------------------
with tab2:
    glossary = st.session_state.glossary_data or []

    if not glossary:
        st.info("No extracted terms available. Run the agentic pipeline on a PDF to generate the glossary.")
    else:
        st.markdown(
            f"""
            <div style="margin-bottom: 20px;">
                <div style="font-size: 0.8rem; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.08em;">
                    AI/ML Glossary
                </div>
                <h2 style="font-size: 1.8rem; margin: 4px 0 0; background: linear-gradient(135deg, #6366F1 0%, #A855F7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    {st.session_state.paper_title or "Paper Analysis"}
                </h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

        g_col1, g_col2 = st.columns([3, 2])
        with g_col1:
            term_search = st.text_input(
                "Filter Terms",
                placeholder="🔍 Search glossary terms...",
                key="term_search_input",
                label_visibility="collapsed"
            )
        with g_col2:
            min_score = st.slider("Min Jargon Score", 1, 10, 1, key="score_slider")

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        for idx, item in enumerate(glossary):
            term = item.get("term", "Unknown Term")
            score = item.get("jargon_score", 5)
            c_def = item.get("context_definition", "No context definition provided.")
            g_def = item.get("general_definition", "No general definition provided.")
            occurrences = item.get("occurrences", [])

            # Filter checks
            if term_search.strip() and term_search.lower() not in term.lower():
                continue
            if score < min_score:
                continue

            score_class = "score-high" if score >= 8 else ("score-mid" if score >= 5 else "score-low")

            with st.container():
                t_col1, t_col2 = st.columns([8, 3])
                with t_col1:
                    st.markdown(
                        f"""
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-family: 'Outfit'; font-size: 1.25rem; font-weight: 700; color: #F3F4F6;">
                                {term}
                            </span>
                            <span class="jargon-badge {score_class}">
                                Jargon Score: {score}/10
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with t_col2:
                    copy_key = f"copy_btn_{idx}_{term}"
                    is_copied = st.session_state.copied_terms.get(copy_key, False)
                    btn_text = "✅ Copied!" if is_copied else "📋 Copy Definitions"

                    if st.button(btn_text, key=copy_key):
                        st.session_state.copied_terms[copy_key] = True
                        st.toast(f"Copied definitions for '{term}' to clipboard buffer!", icon="📋")
                        st.rerun()

                st.markdown(
                    f"""
                    <div class="glass-panel">
                        <div class="def-box">
                        <div class="def-title">🎯 In-Context Paper Definition</div>
                        <div style="font-size: 0.95rem; line-height: 1.55;">{c_def}</div>
                        </div>
                        <div class="def-box" style="border-left-color: #A855F7;">
                        <div class="def-title" style="color: #C084FC;">🌐 General AI/ML Definition</div>
                        <div style="font-size: 0.95rem; line-height: 1.55;">{g_def}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if occurrences:
                    with st.expander(f"📍 Occurrences in Paper ({len(occurrences)})"):
                        for occ in occurrences:
                            st.markdown(f"> *\"{occ}\"*")

# ------------------------------------------------------------------------------
# 8. SLEEK FOOTER WITH GLASS BUTTONS
# ------------------------------------------------------------------------------
st.markdown(
    """
    <div class="footer-container">
        <div style="font-family: 'Outfit'; font-weight: 700; font-size: 1.1rem; color: #818CF8;">
            Paper Lens
        </div>
        <div style="font-size: 0.85rem; color: #9CA3AF; margin-top: 6px;">
            Designed for Next-Generation AI &amp; Science Research Analysis
        </div>
        <div class="footer-links">
            <a href="https://github.com/Nodal-leaf/Paper-Lens"
               target="_blank"
               rel="noopener noreferrer"
               class="footer-glass-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
                </svg>
                GitHub Repository
            </a>
            <a href="https://github.com/Nodal-leaf/Paper-Lens#readme"
               target="_blank"
               rel="noopener noreferrer"
               class="footer-glass-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                </svg>
                Documentation
            </a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
