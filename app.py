from __future__ import annotations

from pathlib import Path
import sys
from datetime import date, datetime

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nbim_digest.actions import ActionCode, get_action
from nbim_digest.config import DB_PATH, ensure_data_dir
from nbim_digest.env import get_anthropic_api_key, get_env_secret, load_app_env
from nbim_digest.pipeline import DigestPipeline
from nbim_digest.storage import DigestStore
from nbim_digest.ui_formatting import action_badge_html, human_rule_decision, human_source


load_app_env(ROOT)
ensure_data_dir()

st.set_page_config(
    page_title="NBIM Daily News Digest",
    page_icon="NBIM",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.7rem; max-width: 1120px; }
    section[data-testid="stSidebar"] { width: 14rem !important; min-width: 14rem !important; }
    section[data-testid="stSidebar"] > div { width: 14rem !important; padding: 0 0.85rem 1rem 0.85rem; }
    [data-testid="stSidebarContent"] { padding-top: 0 !important; }
    [data-testid="stSidebar"] [data-testid="stImage"] { margin-top: -0.35rem; margin-bottom: 0.35rem; }
    [data-testid="stSidebar"] [data-testid="stImage"] img { display: block; }
    [data-testid="stSidebar"] h3 { font-size: 0.95rem; margin-bottom: 0.35rem; }
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] p { font-size: 0.86rem; }
    [data-testid="stSidebar"] div[data-testid="stButton"] button {
      background: #005eb8;
      border-color: #005eb8;
      color: #ffffff;
      border-radius: 6px;
      font-weight: 650;
    }
    [data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
      background: #004f9e;
      border-color: #004f9e;
      color: #ffffff;
    }
    [data-testid="stSidebar"] input[type="radio"],
    [data-testid="stSidebar"] input[type="checkbox"] {
      accent-color: #005eb8;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] > div:first-child {
      border-color: #005eb8 !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) > div:first-child {
      background-color: #005eb8 !important;
      border-color: #005eb8 !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) > div:first-child > div {
      background-color: #ffffff !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) p {
      color: #003f7d !important;
      font-weight: 650;
    }
    [data-testid="stSidebar"] label[data-baseweb="checkbox"] > div:first-child {
      border-color: #005eb8 !important;
    }
    [data-testid="stSidebar"] label[data-baseweb="checkbox"]:has(input:checked) > div:first-child {
      background-color: #005eb8 !important;
      border-color: #005eb8 !important;
    }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] {
      background-color: #005eb8 !important;
      border-color: #005eb8 !important;
      color: #ffffff !important;
    }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] span,
    [data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
      color: #ffffff !important;
      fill: #ffffff !important;
    }
    [data-testid="stMultiSelect"] div[data-baseweb="select"]:focus-within,
    [data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {
      border-color: #005eb8 !important;
      box-shadow: 0 0 0 1px #005eb8 inset !important;
    }
    div[data-baseweb="calendar"] [aria-selected="true"] {
      background-color: #005eb8 !important;
      color: #ffffff !important;
    }
    div[data-baseweb="calendar"] [aria-selected="true"]:hover {
      background-color: #004f9e !important;
      color: #ffffff !important;
    }
    div[data-testid="stExpander"] details summary {
      color: #005eb8 !important;
      font-weight: 650;
    }
    div[data-testid="stExpander"] details summary svg {
      color: #005eb8 !important;
      fill: #005eb8 !important;
    }
    .sidebar-brand { font-weight: 700; font-size: 0.95rem; margin: 0.25rem 0 0.65rem 0; }
    .sidebar-rule { border-top: 1px solid #e5e7eb; margin: 0.7rem 0; }
    .app-kicker { color: #5f6368; font-size: 0.95rem; margin-top: -0.4rem; }
    h1, h2, h3 { letter-spacing: 0; }
    .muted { color: #5f6368; font-size: 0.92rem; }
    a { text-decoration: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def find_logo_path() -> Path | None:
    candidates = [
        ROOT / "assets" / "logo" / "NBIM.png",
        ROOT / "nbim_digest" / "logo",
        ROOT / "src" / "nbim_digest" / "logo",
        ROOT / "logo",
        ROOT / "assets" / "logo",
    ]
    extensions = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in extensions:
            return candidate
        if candidate.is_dir():
            for path in sorted(candidate.iterdir()):
                if path.is_file() and path.suffix.lower() in extensions:
                    return path
    return None


def build_pipeline() -> tuple[DigestPipeline, DigestStore]:
    store = DigestStore(DB_PATH)
    pipeline = DigestPipeline(
        store=store,
        anthropic_api_key=get_anthropic_api_key(),
        data_dir=Path("data"),
        config_dir=Path("config"),
    )
    return pipeline, store


def render_sidebar() -> dict:
    logo_path = find_logo_path()
    if logo_path:
        st.sidebar.image(str(logo_path), width=72)
    else:
        st.sidebar.markdown("<div class='sidebar-brand'>NBIM Digest</div>", unsafe_allow_html=True)

    page = st.sidebar.radio("Page", ["Digest", "Audit trail"], label_visibility="collapsed")
    st.sidebar.markdown("<div class='sidebar-rule'></div>", unsafe_allow_html=True)

    controls = {
        "page": page,
        "mode": "demo",
        "use_cached": False,
        "time_horizon": "24h",
        "review_depth": "fast",
        "run_clicked": False,
    }

    if page != "Digest":
        return controls

    raw_anthropic_key = get_env_secret("ANTHROPIC_API_KEY")
    valid_anthropic_key = get_anthropic_api_key()
    if raw_anthropic_key and not valid_anthropic_key:
        st.sidebar.warning("ANTHROPIC_API_KEY should start with `sk-ant-`. Using fallback.")

    st.sidebar.markdown("### Digest")
    mode_label = st.sidebar.radio("Mode", ["Live", "Demo"], index=0)
    mode = "live" if mode_label == "Live" else "demo"
    controls["mode"] = mode

    if mode == "demo":
        controls["use_cached"] = st.sidebar.toggle(
            "Cached outputs",
            value=not bool(valid_anthropic_key),
            help="Use stored demo outputs so the demo works without API keys.",
        )
    else:
        controls["time_horizon"] = st.sidebar.radio("Duration", ["24h", "48h", "7d"], horizontal=True)
        review_depth_label = st.sidebar.radio(
            "Review",
            ["Fast", "Full"],
            index=0,
            horizontal=True,
            help="Fast skips the extra reviewer call. Full adds the slower adversarial review pass.",
        )
        controls["review_depth"] = "full" if review_depth_label == "Full" else "fast"

    button_label = "Run demo" if mode == "demo" else "Run live"
    controls["run_clicked"] = st.sidebar.button(button_label, type="primary", use_container_width=True)

    last_result = st.session_state.get("last_result")
    if last_result is not None:
        cost = last_result.cost
        api_calls = cost.relevance_articles + cost.summary_articles + cost.reviewer_articles
        st.sidebar.markdown("<div class='sidebar-rule'></div>", unsafe_allow_html=True)
        st.sidebar.caption(
            f"Last run · ${cost.estimated_cost_usd:.2f} · {api_calls} API call{'s' if api_calls != 1 else ''}"
        )

    return controls


def sort_digest_items(items):
    return sorted(
        items,
        key=lambda item: (
            get_action(item.final_action).severity,
            item.llm_relevance_score,
            item.article.published_at or "",
        ),
        reverse=True,
    )


def render_digest_item(item, *, run_id: int, idx: int, feedback_enabled: bool) -> None:
    article = item.article
    action = get_action(item.final_action)
    with st.container(border=True):
        top_left, top_right = st.columns([0.75, 0.25])
        with top_left:
            st.subheader(article.title)
            st.markdown(
                f"<span class='muted'>{human_source(article.source)}"
                f" · {article.published_at or 'Date unavailable'} · "
                f"<a href='{article.url}' target='_blank'>Open article</a></span>",
                unsafe_allow_html=True,
            )
        with top_right:
            st.markdown(action_badge_html(item.final_action), unsafe_allow_html=True)

        st.markdown(item.summary)
        st.markdown("**Recommended next step**")
        st.write(item.recommended_next_step or action.default_next_step)

        with st.expander("Why this article was included"):
            st.write(f"**Source:** {article.source}")
            discovery = article.discovery_path
            if article.discovery_query:
                discovery = f"{discovery}: {article.discovery_query}"
            st.write(f"**Discovery path:** {discovery}")
            signals = ", ".join(item.rule_decision.matched_signals) or "No deterministic signals recorded"
            st.write(f"**Matched signals:** {signals}")
            st.write(f"**Rule filter result:** {human_rule_decision(item.rule_decision.decision)}")
            st.write(f"**LLM relevance score:** {item.llm_relevance_score}/10")
            st.write(f"**Initial action:** {get_action(item.initial_action).label}")
            if item.reviewer_skipped:
                st.write("**Reviewer action:** skipped in Fast mode")
            else:
                reviewer_label = get_action(item.reviewer_action).label
                if item.reviewer_action != item.initial_action:
                    st.write(f"**Reviewer action:** changed to {reviewer_label}")
                else:
                    st.write(f"**Reviewer action:** kept as {reviewer_label}")
            st.write(f"**Reason for action:** {item.reason_for_action}")

        if not feedback_enabled:
            return

        feedback_col, note_col, save_col = st.columns([0.25, 0.55, 0.2])
        with feedback_col:
            feedback = st.selectbox(
                "Feedback",
                ["Agree", "Too high", "Too low", "Not relevant"],
                key=f"feedback-{run_id}-{idx}",
            )
        with note_col:
            note = st.text_input("Note", key=f"note-{run_id}-{idx}", placeholder="Optional")
        with save_col:
            st.write("")
            if st.button("Save feedback", key=f"save-{run_id}-{idx}"):
                if item.article_id is not None:
                    _, store = build_pipeline()
                    store.initialize()
                    store.save_feedback(run_id, item.article_id, feedback, note)
                    st.toast("Feedback saved to audit database.")


def render_digest_result(result, *, feedback_enabled: bool = True) -> None:
    if result.dropped_count:
        st.caption(f"{result.dropped_count} article(s) were dropped but kept in the audit trail.")
    if result.mode == "live" and result.debug:
        st.caption(
            "Fetched "
            f"{result.debug.get('rss_candidates', 0)} Norwegian RSS candidate(s) and "
            f"{result.debug.get('google_news_candidates', 0)} Google News RSS candidate(s) "
            f"for {result.debug.get('time_horizon', 'the selected horizon')}."
        )
    if not result.items:
        st.info("No articles passed the digest filter for this run. Check the audit trail to inspect dropped candidates.")

    for idx, item in enumerate(sort_digest_items(result.items), start=1):
        render_digest_item(item, run_id=result.run_id, idx=idx, feedback_enabled=feedback_enabled)


def digest_page(controls: dict) -> None:
    st.title("NBIM Daily News Digest")
    st.markdown(
        "<div class='app-kicker'>Metadata-only monitoring, deterministic filtering, LLM review, and an auditable action trail.</div>",
        unsafe_allow_html=True,
    )
    mode = controls["mode"]
    use_cached = controls["use_cached"]
    time_horizon = controls["time_horizon"]
    review_depth = controls["review_depth"]
    if mode == "demo":
        st.info(
            "Demo mode uses a curated set of historical articles to demonstrate the full action taxonomy."
        )
        if use_cached:
            st.caption("Using cached demo outputs because cached mode is selected.")
    else:
        st.caption(
            f"Live monitoring · Google News {time_horizon} · "
            f"{'Fast review' if review_depth == 'fast' else 'Full adversarial review'}"
        )

    if controls["run_clicked"]:
        pipeline, _ = build_pipeline()
        progress = st.progress(0)
        status_box = st.empty()
        partial_box = st.empty()
        partial_items = []
        try:
            final_result = None
            for event in pipeline.stream(
                    mode=mode,
                    use_cached_demo_outputs=use_cached,
                    time_horizon=time_horizon,
                    review_depth=review_depth,
            ):
                if event.kind == "started":
                    status_box.info(event.status_message)
                    progress.progress(0)
                elif event.kind in {"item", "progress"}:
                    if event.candidate_count:
                        progress.progress(min(event.processed_count / event.candidate_count, 1.0))
                    status_box.info(event.status_message)
                    if event.kind == "item" and event.item is not None:
                        partial_items.append(event.item)
                        with partial_box.container():
                            st.caption("Partial results. Final sorting is applied when the run finishes.")
                            for idx, item in enumerate(sort_digest_items(partial_items), start=1):
                                render_digest_item(item, run_id=event.run_id, idx=idx, feedback_enabled=False)
                elif event.kind == "done" and event.result is not None:
                    final_result = event.result
            if final_result is not None:
                st.session_state["last_result"] = final_result
                progress.empty()
                status_box.empty()
                partial_box.empty()
        except Exception as exc:
            st.error(f"Digest run failed: {exc}")

    result = st.session_state.get("last_result")
    if not result:
        st.markdown("Run the demo digest to see the full pipeline without API keys.")
        return

    render_digest_result(result)


def audit_page() -> None:
    st.title("Audit Trail")
    st.caption("Every rule decision, LLM decision, and final action is inspectable.")

    _, store = build_pipeline()
    store.initialize()
    rows = store.fetch_audit_rows()
    if not rows:
        st.info("No audit rows yet. Run a demo digest first.")
        return

    table_rows = [_format_audit_row(row) for row in rows]

    f1, f2, f3, f4, f5 = st.columns(5)
    sources = f1.multiselect("Source", sorted({row["Source"] for row in table_rows}))
    actions = f2.multiselect("Action", sorted({row["Final action"] for row in table_rows}))
    included = f3.multiselect("Included / dropped", ["Included", "Dropped"])
    run_type = f4.multiselect("Demo / live", ["Demo", "Live"])
    min_date = f5.date_input("From date", value=None)

    filtered = table_rows
    if sources:
        filtered = [row for row in filtered if row["Source"] in sources]
    if actions:
        filtered = [row for row in filtered if row["Final action"] in actions]
    if included:
        filtered = [row for row in filtered if row["Included"] in included]
    if run_type:
        filtered = [row for row in filtered if row["Run type"] in run_type]
    if min_date:
        filtered = [row for row in filtered if row["Date"] is None or row["Date"] >= min_date]

    st.markdown(_audit_markdown_table(filtered[:200]))


def _format_audit_row(row: dict) -> dict:
    published = _parse_date(row.get("published_at"))
    reviewer_action = (
        "Skipped (fast mode)"
        if row.get("reviewer_skipped")
        else get_action(row.get("reviewer_action") or ActionCode.NO_ACTION.value).label
    )
    return {
        "Time": _format_time(row.get("time")),
        "Article": row.get("article") or "",
        "Source": human_source(row.get("source") or ""),
        "Rule decision": human_rule_decision(row.get("rule_decision") or "skip"),
        "LLM relevance": int(row.get("llm_relevance") or 0),
        "Initial action": get_action(row.get("initial_action") or ActionCode.NO_ACTION.value).label,
        "Reviewer action": reviewer_action,
        "Final action": get_action(row.get("final_action") or ActionCode.NO_ACTION.value).label,
        "Included": "Included" if row.get("included") else "Dropped",
        "Run type": "Demo" if row.get("mode") == "demo" else "Live",
        "URL": row.get("url") or "",
        "Date": published,
    }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _format_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)[:16]


def _escape_md(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _audit_markdown_table(rows: list[dict]) -> str:
    if not rows:
        return "No rows match the selected filters."
    header = (
        "| Time | Article | Source | Rule decision | LLM relevance | Initial action | "
        "Reviewer action | Final action | Included | Run type |\n"
        "|---|---|---|---|---:|---|---|---|---|---|"
    )
    body = []
    for row in rows:
        article = _escape_md(row["Article"])
        if row["URL"]:
            article = f"[{article}]({row['URL']})"
        body.append(
            "| "
            + " | ".join(
                [
                    _escape_md(row["Time"]),
                    article,
                    _escape_md(row["Source"]),
                    _escape_md(row["Rule decision"]),
                    _escape_md(row["LLM relevance"]),
                    _escape_md(row["Initial action"]),
                    _escape_md(row["Reviewer action"]),
                    _escape_md(row["Final action"]),
                    _escape_md(row["Included"]),
                    _escape_md(row["Run type"]),
                ]
            )
            + " |"
        )
    return header + "\n" + "\n".join(body)


controls = render_sidebar()
if controls["page"] == "Digest":
    digest_page(controls)
else:
    audit_page()
