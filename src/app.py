"""
src/app.py - Paper Lens Streamlit Web Application

A premium, dark-mode glass-morphism interface for Paper Lens.
Features:
- Dark/Light Theme toggle with glassmorphism CSS (.glass-card, .glass-panel).
- Top Nav with Logo, API Health Status indicator, and Theme Toggle.
- Hero/Upload Card with simulated real-time progress bar & hover-scaling accent gradient button.
- Data Tabs:
  1. Sections: Collapsible section tree with real-time search filtering.
  2. Glossary: Term accordion with Jargon Scores, Context/General definitions, & Copy buttons.
- Footer with muted gradient and hover-scaling links.
"""

import base64
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
if "theme" not in st.session_state:
    st.session_state.theme = "dark"
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
# 2. CUSTOM CSS (Glassmorphism, Typography, Animations, Themes)
# ------------------------------------------------------------------------------
def get_css(theme: str) -> str:
    is_dark = theme == "dark"
    bg_color = "#0B0F17" if is_dark else "#F8FAFC"
    card_bg = "rgba(22, 27, 38, 0.65)" if is_dark else "rgba(255, 255, 255, 0.85)"
    panel_bg = "rgba(30, 37, 51, 0.5)" if is_dark else "rgba(241, 245, 249, 0.7)"
    text_color = "#F3F4F6" if is_dark else "#0F172A"
    muted_color = "#9CA3AF" if is_dark else "#64748B"
    border_color = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"
    input_bg = "rgba(15, 23, 42, 0.6)" if is_dark else "rgba(255, 255, 255, 0.9)"

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
        background-image: {
            "radial-gradient(at 0% 0%, rgba(79, 70, 229, 0.15) 0px, transparent 50%), "
            "radial-gradient(at 100% 100%, rgba(124, 58, 237, 0.15) 0px, transparent 50%)"
            if is_dark else
            "radial-gradient(at 0% 0%, rgba(79, 70, 229, 0.05) 0px, transparent 50%), "
            "radial-gradient(at 100% 100%, rgba(124, 58, 237, 0.05) 0px, transparent 50%)"
        } !important;
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
        box-shadow: 0 20px 50px rgba(0, 0, 0, {0.4 if is_dark else 0.06});
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
        padding: 24px;
        border-top: 1px solid {border_color};
        background: linear-gradient(180deg, transparent 0%, {card_bg} 100%);
        border-radius: 20px 20px 0 0;
        text-align: center;
    }}

    .footer-links {{
        display: flex;
        justify-content: center;
        gap: 32px;
        margin-top: 12px;
    }}

    .footer-link {{
        color: {muted_color};
        text-decoration: none;
        font-weight: 500;
        font-size: 0.9rem;
        transition: all 0.2s ease;
    }}

    .footer-link:hover {{
        color: #818CF8;
        transform: scale(1.08);
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




st.markdown(get_css(st.session_state.theme), unsafe_allow_html=True)


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

nav_col1, nav_col2, nav_col3 = st.columns([6, 3, 2])

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

with nav_col3:
    toggle_label = "☀️ Light Mode" if st.session_state.theme == "dark" else "🌙 Dark Mode"
    if st.button(toggle_label, key="theme_toggle"):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# 5. HERO / UPLOAD CARD SECTION
# ------------------------------------------------------------------------------
st.markdown('<div class="glass-card">', unsafe_allow_html=True)

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

st.markdown('</div>', unsafe_allow_html=True)


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
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    
    search_query = st.text_input(
        "Search Section",
        placeholder="🔍 Type keywords to filter section titles and content (e.g. 'Encoder', 'Loss', 'Masking')...",
        key="section_search_input",
        label_visibility="collapsed"
    )

    def render_section(sec: dict, level: int = 0):
        title = sec.get("title", "Untitled Section")
        num = sec.get("number")
        page = sec.get("page_number")
        content = sec.get("content", "")
        subsections = sec.get("subsections", [])

        display_num = f"{num}. " if num else ""
        header_text = f"{display_num}{title}"
        if page:
            header_text += f" (p. {page})"

        # Check search filter
        matches_filter = True
        if search_query.strip():
            q = search_query.lower().strip()
            matches_title = q in title.lower() or (num and q in str(num))
            matches_content = q in content.lower()
            matches_sub = any(
                q in sub.get("title", "").lower() or q in sub.get("content", "").lower()
                for sub in subsections
            )
            matches_filter = matches_title or matches_content or matches_sub

        if not matches_filter:
            return

        with st.expander(header_text, expanded=(level == 0 and bool(search_query))):
            if content:
                st.markdown(content)
            else:
                st.markdown("*No direct text content in section header.*")

            if subsections:
                st.markdown("<div style='margin-left: 20px; margin-top: 10px;'>", unsafe_allow_html=True)
                for sub in subsections:
                    render_section(sub, level=level + 1)
                st.markdown("</div>", unsafe_allow_html=True)

    sections = st.session_state.parsed_data or []
    if sections:
        for sec in sections:
            render_section(sec)
    else:
        st.info("No section data available.")

    st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# TAB 2: AI/ML GLOSSARY WITH COPY FUNCTIONALITY
# ------------------------------------------------------------------------------
with tab2:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)

    glossary = st.session_state.glossary_data or []

    if not glossary:
        st.info("No extracted terms available. Run the agentic pipeline on a PDF to generate the glossary.")
    else:
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
                st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
                
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
                    <div class="def-box">
                        <div class="def-title">🎯 In-Context Paper Definition</div>
                        <div style="font-size: 0.95rem; line-height: 1.55;">{c_def}</div>
                    </div>
                    <div class="def-box" style="border-left-color: #A855F7;">
                        <div class="def-title" style="color: #C084FC;">🌐 General AI/ML Definition</div>
                        <div style="font-size: 0.95rem; line-height: 1.55;">{g_def}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if occurrences:
                    with st.expander(f"📍 Occurrences in Paper ({len(occurrences)})"):
                        for occ in occurrences:
                            st.markdown(f"> *\"{occ}\"*")

                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)





# ------------------------------------------------------------------------------
# 8. SLEEK FOOTER WITH SCALING LINKS
# ------------------------------------------------------------------------------
st.markdown(
    """
    <div class="footer-container">
        <div style="font-family: 'Outfit'; font-weight: 700; font-size: 1.1rem; color: #818CF8;">
            Paper Lens
        </div>
        <div style="font-size: 0.85rem; color: #9CA3AF; margin-top: 4px;">
            Designed for Next-Generation AI & Science Research Analysis
        </div>
        <div class="footer-links">
            <a href="https://github.com" target="_blank" class="footer-link">🐙 GitHub Repository</a>
            <a href="#" class="footer-link">📚 Documentation</a>
            <a href="#" class="footer-link">✉️ Contact & Support</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
