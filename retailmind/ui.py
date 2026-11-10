"""Premium UI helpers: branding, theme CSS and reusable widgets.

Streamlit renders a linear document, so the Power BI-style shell is built from a
wide canvas, a navigation sidebar, a central report area and a right-hand
Fields/Visualizations panel.  All styling is additive: if a Streamlit selector
changes, the application remains functional.
"""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

from retailmind.config import APP_NAME, APP_TITLE, TAGLINE, VERSION
from retailmind.models import Theme


_PALETTE = {
    "dark": {
        "bg": "#0b1020", "bg2": "#0f1730", "panel": "#141b31", "panel2": "#10172b",
        "text": "#e7ecff", "muted": "#94a3b8", "border": "rgba(148,163,184,0.18)",
        "input": "#0f1730", "shadow": "0 18px 50px rgba(2,6,23,0.35)",
    },
    "midnight": {
        "bg": "#060913", "bg2": "#0a1020", "panel": "#0e1526", "panel2": "#0b1222",
        "text": "#e2e8f0", "muted": "#8ca3c7", "border": "rgba(96,165,250,0.18)",
        "input": "#0b1222", "shadow": "0 18px 50px rgba(0,0,0,0.45)",
    },
    "light": {
        "bg": "#f5f7fc", "bg2": "#eef2f9", "panel": "#ffffff", "panel2": "#f8fafc",
        "text": "#0f172a", "muted": "#64748b", "border": "#e2e8f0",
        "input": "#ffffff", "shadow": "0 14px 40px rgba(15,23,42,0.08)",
    },
    "corporate": {
        "bg": "#f3f6fb", "bg2": "#e9eff7", "panel": "#ffffff", "panel2": "#f7f9fc",
        "text": "#172033", "muted": "#5b6b82", "border": "#dbe3ee",
        "input": "#ffffff", "shadow": "0 14px 40px rgba(23,32,51,0.08)",
    },
}


def setup_page() -> None:
    st.set_page_config(
        page_title=f"{APP_NAME} – Intelligent Business Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": f"{APP_TITLE}\n\n{TAGLINE}\n\nVersion {VERSION}",
        },
    )


def _render_html(markup: str) -> None:
    """Render trusted HTML without letting Markdown reinterpret it.

    Compacting the markup removes all blank lines and leading whitespace,
    preventing Markdown from treating indented tags as code blocks.
    Inline styles ensure correct presentation regardless of CSS timing.
    """
    compact = " ".join(line.strip() for line in str(markup).splitlines() if line.strip())
    st.markdown(compact, unsafe_allow_html=True)


def logo_svg(accent: str = "#7c5cff", size: int = 44) -> str:
    """Return a compact inline SVG logo (three rising bars + insight spark).

    The markup is deliberately a single line: multi-line SVG injected into
    ``st.markdown`` contains blank lines that terminate the surrounding HTML
    block and leak raw tags into the page.
    """
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 48 48" fill="none" '
        'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="RetailMind AI logo">'
        '<defs><linearGradient id="rmg" x1="4" y1="44" x2="44" y2="4" gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{accent}"/><stop offset="1" stop-color="#22d3ee"/>'
        '</linearGradient></defs>'
        '<rect x="2" y="2" width="44" height="44" rx="12" fill="url(#rmg)" fill-opacity="0.16"/>'
        '<rect x="2" y="2" width="44" height="44" rx="12" stroke="url(#rmg)" stroke-opacity="0.45"/>'
        '<rect x="11" y="27" width="6" height="11" rx="2" fill="url(#rmg)"/>'
        '<rect x="21" y="20" width="6" height="18" rx="2" fill="url(#rmg)"/>'
        '<rect x="31" y="13" width="6" height="25" rx="2" fill="url(#rmg)"/>'
        '<path d="M11 18 L20 13 L28 16 L37 8" stroke="#e7ecff" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="37" cy="8" r="2.5" fill="#e7ecff"/></svg>'
    )


def inject_css(theme: Theme) -> None:
    palette = _PALETTE.get(theme.preset, _PALETTE["dark"])
    accent = theme.accent or "#7c5cff"
    font = theme.font or "Inter, Segoe UI, sans-serif"
    st.markdown(
        f"""
        <style>
        :root {{
            --rm-bg: {palette['bg']};
            --rm-bg2: {palette['bg2']};
            --rm-panel: {palette['panel']};
            --rm-panel2: {palette['panel2']};
            --rm-text: {palette['text']};
            --rm-muted: {palette['muted']};
            --rm-border: {palette['border']};
            --rm-input: {palette['input']};
            --rm-accent: {accent};
            --rm-shadow: {palette['shadow']};
            --rm-font: {font};
        }}
        html, body, [class*="css"] {{ font-family: var(--rm-font); }}
        .stApp {{
            background: radial-gradient(1200px 600px at 12% -10%, color-mix(in srgb, var(--rm-accent) 16%, transparent) 0%, transparent 55%),
                        radial-gradient(900px 500px at 100% 0%, rgba(34,211,238,0.08) 0%, transparent 50%),
                        var(--rm-bg);
            color: var(--rm-text);
        }}
        [data-testid="stHeader"] {{ background: transparent; }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--rm-panel2) 0%, var(--rm-bg) 100%);
            border-right: 1px solid var(--rm-border);
        }}
        [data-testid="stSidebar"] > div:first-child {{ padding-top: 1rem; }}
        h1, h2, h3, h4 {{ font-family: var(--rm-font); letter-spacing: -0.025em; color: var(--rm-text); }}
        h1 {{ font-size: 2.05rem !important; font-weight: 800 !important; }}
        h2 {{ font-size: 1.35rem !important; font-weight: 700 !important; }}
        h3 {{ font-size: 1.05rem !important; font-weight: 650 !important; }}
        p, label, span, div {{ color: inherit; }}
        .rm-muted {{ color: var(--rm-muted) !important; }}
        .rm-brand-card {{
            display: flex; align-items: center; gap: 12px;
            padding: 12px 12px 14px 12px; border: 1px solid var(--rm-border);
            border-radius: 16px; background: color-mix(in srgb, var(--rm-panel) 88%, transparent);
            box-shadow: var(--rm-shadow); margin-bottom: 14px;
        }}
        .rm-brand-card {{ width: fit-content; max-width: 100%; }}
        .rm-brand-copy {{ display: flex; flex-direction: column; min-width: 0; }}
        .rm-brand-name {{ font-weight: 800; font-size: 1.22rem; letter-spacing: -0.02em; line-height: 1.15; }}
        .rm-brand-tag {{ font-size: 0.76rem; color: var(--rm-muted); margin-top: 2px; }}
        .rm-toolbar {{
            display: flex; align-items: center; justify-content: space-between; gap: 14px;
            padding: 12px 16px; border: 1px solid var(--rm-border); border-radius: 16px;
            background: color-mix(in srgb, var(--rm-panel) 86%, transparent);
            box-shadow: var(--rm-shadow); margin-bottom: 14px;
        }}
        .rm-toolbar-left, .rm-toolbar-right {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
        .rm-pill {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 650;
            border: 1px solid var(--rm-border); background: color-mix(in srgb, var(--rm-panel2) 80%, transparent);
            color: var(--rm-muted); white-space: nowrap;
        }}
        .rm-pill-ok {{ color: #34d399; border-color: rgba(52,211,153,0.35); background: rgba(52,211,153,0.08); }}
        .rm-pill-warn {{ color: #fbbf24; border-color: rgba(251,191,36,0.35); background: rgba(251,191,36,0.08); }}
        .rm-pill-accent {{ color: var(--rm-accent); border-color: color-mix(in srgb, var(--rm-accent) 40%, transparent); background: color-mix(in srgb, var(--rm-accent) 10%, transparent); }}
        div[data-testid="stMetric"] {{
            background: linear-gradient(160deg, color-mix(in srgb, var(--rm-panel) 96%, transparent), color-mix(in srgb, var(--rm-panel2) 94%, transparent));
            border: 1px solid var(--rm-border); border-radius: 16px; padding: 14px 16px;
            box-shadow: var(--rm-shadow);
        }}
        div[data-testid="stMetric"] label {{ color: var(--rm-muted) !important; font-size: 0.76rem !important; font-weight: 600 !important; }}
        div[data-testid="stMetricValue"] {{
            color: var(--rm-text) !important; font-weight: 800 !important;
            letter-spacing: -0.03em; font-size: 1.45rem !important; line-height: 1.15;
            overflow: visible !important; white-space: normal !important; overflow-wrap: anywhere;
        }}
        div[data-testid="stMetricValue"] > div {{ overflow: visible !important; text-overflow: clip !important; white-space: normal !important; }}
        div[data-testid="stMetricLabel"] {{ white-space: normal !important; }}
        div[data-testid="stMetricDelta"] {{ font-weight: 650; }}
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 16px; border-color: var(--rm-border) !important;
        }}
        [data-testid="stExpander"] {{
            border: 1px solid var(--rm-border); border-radius: 14px;
            background: color-mix(in srgb, var(--rm-panel) 70%, transparent);
        }}
        .stButton > button {{
            border-radius: 10px; border: 1px solid var(--rm-border);
            background: color-mix(in srgb, var(--rm-panel2) 86%, transparent);
            color: var(--rm-text); font-weight: 600; transition: all .15s ease;
        }}
        .stButton > button:hover {{ border-color: var(--rm-accent); color: var(--rm-accent); transform: translateY(-1px); }}
        .stButton > button[kind="primary"] {{ background: var(--rm-accent); border-color: var(--rm-accent); color: white; }}
        .stDownloadButton > button {{ border-radius: 10px; }}
        [data-testid="stFileUploaderDropzone"] {{
            background: color-mix(in srgb, var(--rm-panel2) 76%, transparent);
            border: 1px dashed color-mix(in srgb, var(--rm-accent) 45%, var(--rm-border));
            border-radius: 14px;
        }}
        [data-testid="stDataFrame"] {{ border: 1px solid var(--rm-border); border-radius: 12px; overflow: hidden; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
        .stTabs [data-baseweb="tab"] {{ border-radius: 10px 10px 0 0; padding: 6px 14px; }}
        .rm-insight {{
            border: 1px solid var(--rm-border); border-left: 3px solid var(--rm-accent);
            border-radius: 12px; padding: 11px 14px; margin: 8px 0;
            background: color-mix(in srgb, var(--rm-panel) 72%, transparent);
        }}
        .rm-insight-positive {{ border-left-color: #22c55e; }}
        .rm-insight-warning {{ border-left-color: #f59e0b; }}
        .rm-insight-negative {{ border-left-color: #f43f5e; }}
        .rm-insight-title {{ font-weight: 700; font-size: 0.88rem; margin-bottom: 3px; }}
        .rm-insight-text {{ font-size: 0.83rem; color: var(--rm-text); opacity: .92; }}
        .rm-insight-evidence {{ font-size: 0.70rem; color: var(--rm-muted); margin-top: 5px; }}
        .rm-page-tab {{
            display: inline-flex; align-items: center; gap: 7px; padding: 7px 13px; margin-right: 6px;
            border: 1px solid var(--rm-border); border-radius: 10px 10px 0 0;
            background: color-mix(in srgb, var(--rm-panel2) 75%, transparent);
            font-size: 0.78rem; font-weight: 600; color: var(--rm-muted);
        }}
        .rm-page-tab-active {{ color: var(--rm-text); border-bottom-color: var(--rm-accent); box-shadow: inset 0 -2px 0 var(--rm-accent); }}
        .rm-empty {{
            border: 1px dashed color-mix(in srgb, var(--rm-accent) 35%, var(--rm-border));
            border-radius: 18px; padding: 26px; background: color-mix(in srgb, var(--rm-panel) 62%, transparent);
            text-align: left;
        }}
        .rm-chat-user {{
            background: color-mix(in srgb, var(--rm-accent) 18%, transparent);
            border: 1px solid color-mix(in srgb, var(--rm-accent) 32%, transparent);
            border-radius: 12px; padding: 9px 12px; margin: 6px 0 6px auto; max-width: 85%;
            font-size: 0.85rem;
        }}
        .rm-chat-assistant {{
            background: color-mix(in srgb, var(--rm-panel2) 82%, transparent);
            border: 1px solid var(--rm-border); border-radius: 12px; padding: 10px 12px;
            margin: 6px auto 6px 0; max-width: 92%; font-size: 0.85rem;
        }}
        .rm-chat-meta {{ font-size: 0.68rem; color: var(--rm-muted); margin-top: 5px; }}
        .rm-section-label {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.09em; color: var(--rm-muted); font-weight: 700; margin: 6px 0; }}
        .rm-component-title {{ font-size: 0.84rem; font-weight: 700; color: var(--rm-text); margin: 2px 0 6px 0; letter-spacing: -0.01em; }}
        .rm-footer {{ color: var(--rm-muted); font-size: 0.72rem; border-top: 1px solid var(--rm-border); padding-top: 12px; margin-top: 26px; }}
        .rm-kpi-note {{ font-size: 0.68rem; color: var(--rm-muted); margin-top: -6px; }}
        @media (max-width: 900px) {{
            h1 {{ font-size: 1.55rem !important; }}
            .rm-toolbar {{ flex-direction: column; align-items: flex-start; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand(compact: bool = False) -> None:
    accent = st.session_state.get("rm_accent", "#7c5cff")
    tagline = "Universal BI platform" if compact else TAGLINE
    _render_html(
        f'<div class="rm-brand-card" style="display:flex;align-items:center;gap:14px;padding:12px 18px;border-radius:16px;border:1px solid rgba(148,163,184,0.18);background:linear-gradient(135deg,rgba(20,27,49,0.95),rgba(15,23,48,0.92));margin-bottom:14px;">'
        f'{logo_svg(accent, size=38 if compact else 44)}'
        f'<div class="rm-brand-copy" style="display:flex;flex-direction:column;gap:2px;">'
        f'<div class="rm-brand-name" style="font-weight:800;font-size:1.24rem;letter-spacing:-0.02em;color:#e7ecff;line-height:1.2;">{html.escape(APP_NAME)}</div>'
        f'<div class="rm-brand-tag" style="font-size:0.80rem;color:#94a3b8;font-weight:500;">{html.escape(tagline)}</div>'
        f'</div></div>'
    )


def section_label(text: str) -> None:
    _render_html(f"<div class='rm-section-label'>{html.escape(text)}</div>")


def pill(text: str, kind: str = "accent") -> str:
    return f"<span class='rm-pill rm-pill-{kind}'>{html.escape(text)}</span>"


def render_empty_state(title: str, body: str, bullets: Iterable[str] = ()) -> None:
    items = "".join(f"<li>{html.escape(item)}</li>" for item in bullets)
    bullets_html = (
        f'<ul style="margin:12px 0 0 0;color:var(--rm-muted);font-size:0.82rem">{items}</ul>'
        if items
        else ""
    )
    _render_html(
        '<div class="rm-empty">'
        f'<h3 style="margin:0 0 6px 0">{html.escape(title)}</h3>'
        f'<div class="rm-muted" style="font-size:0.88rem">{html.escape(body)}</div>'
        f"{bullets_html}</div>"
    )


def render_footer() -> None:
    _render_html(
        f"<div class='rm-footer'>{html.escape(APP_NAME)} · {html.escape(TAGLINE)} · "
        f"v{html.escape(VERSION)}</div>"
    )


def render_toolbar(
    dataset_name: str | None,
    domain_label: str | None,
    ai_available: bool,
    theme_preset: str,
) -> None:
    dataset_badge = pill(dataset_name or "No dataset", "accent") if dataset_name else pill("Awaiting upload", "warn")
    domain_badge = pill(domain_label or "Universal", "accent") if domain_label else ""
    ai_badge = pill("AI connected" if ai_available else "AI optional", "ok" if ai_available else "warn")
    _render_html(
        '<div class="rm-toolbar">'
        '<div class="rm-toolbar-left">'
        '<span class="rm-pill rm-pill-accent">Report view</span>'
        f"{dataset_badge}{domain_badge}</div>"
        '<div class="rm-toolbar-right">'
        f'{ai_badge}<span class="rm-pill">Theme: {html.escape(theme_preset.title())}</span>'
        "</div></div>"
    )
