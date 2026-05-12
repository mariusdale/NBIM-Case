# NBIM Daily News Digest

Proof of concept for a daily NBIM communications digest. It fetches metadata-only news inputs, applies deterministic NBIM relevance rules, uses Anthropic models for relevance/summarization/action review when configured, and stores decisions in SQLite.

## Quick Start

Create a local environment and install the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
streamlit run app.py
```

Then choose **Demo mode** and click **Run demo digest**. Demo mode works without API keys when cached outputs are enabled.

For live monitoring with Anthropic analysis, create a local `.env` file and add your API key:

```bash
cp .env.example .env
```

Then edit `.env`:

```text
ANTHROPIC_API_KEY=your_anthropic_api_key
```

After the key is set, run `streamlit run app.py`, choose **Live mode**, and click **Run live**.

## What The POC Demonstrates

- Compliant source selection: Norwegian RSS metadata and Google News RSS search metadata, no article scraping.
- Source registry in `config/feeds.yaml`, including disabled-source rationale.
- Google News RSS registry in `config/google_news_rss.yaml`, including `24h`, `48h`, and `7d` horizons.
- Local NBIM priority file in `config/priorities.yaml`.
- Deterministic rule filter in `config/content_filter_taxonomy.yaml` and `src/nbim_digest/rule_filter.py`.
- Five-level action taxonomy in `src/nbim_digest/actions.py`.
- Anthropic pipeline: Haiku 4.5 relevance, Sonnet 4.6 summary/action, Sonnet 4.6 reviewer.
- Fast review mode skips the reviewer by default for lower latency; full adversarial review is available as an explicit option.
- SQLite audit trail for articles, rule decisions, LLM calls, final decisions, and feedback.
- Cached demo mode in `data/demo_cached_outputs.json`.

Anthropic model defaults use the public API aliases `claude-haiku-4-5` and `claude-sonnet-4-6`. Anthropic’s docs list Haiku 4.5 and Sonnet 4.6 IDs and pricing; override them in `config/prompts.yaml` if your account requires a pinned snapshot.

## Pipeline

1. Fetch metadata from enabled Norwegian RSS feeds and Google News RSS search for the selected horizon.
2. Deduplicate by normalized URL.
3. Apply deterministic taxonomy:
   - Tier 1 direct NBIM/Oil Fund references pass.
   - Tier 2 contextual ownership/fund signals contribute strongly.
   - Tier 3 topics only count when paired with Tier 1 or Tier 2.
   - Ambiguous central-bank terms are suppressed unless linked to NBIM.
   - Promotional content is excluded.
4. Send pass/review candidates to Haiku 4.5 for relevance scoring.
5. Send included articles to Sonnet 4.6 for summary and initial action.
6. In Fast mode, use the summary/action decision directly and record that reviewer was skipped. In Full mode, send the proposed action to a Sonnet 4.6 reviewer pass.
7. Store every decision and model call in SQLite.
8. Stream processed articles incrementally into Streamlit, then sort final cards by action severity and relevance.
9. Show digest cards and a filterable audit trail in Streamlit.

## Action Taxonomy

| Code | Severity | Label |
|---|---:|---|
| `NO_ACTION` | 0 | No action |
| `MONITOR` | 1 | Monitor |
| `ALERT_COMMUNICATIONS` | 2 | Alert communications |
| `ALERT_OWNERSHIP_AND_COMPLIANCE` | 3 | Alert ownership & compliance |
| `ESCALATE_TO_LEADERSHIP` | 4 | Escalate to leadership |

Higher levels imply the lower levels are also relevant.

## Demo Mode

Demo mode uses seven curated historical articles from the assignment brief. It is explicitly labeled as historical/demo content in the UI. Cached outputs are stored in `data/demo_cached_outputs.json`, so the demo works without Anthropic keys.

If an Anthropic key is configured, you can disable cached outputs and run the full LLM pipeline over the demo articles.

## Audit Trail

The audit page reads `data/nbim_digest.sqlite` and shows:

| Time | Article | Source | Rule decision | LLM relevance | Initial action | Reviewer action | Final action |
|---|---|---|---|---:|---|---|---|

Filters include source, action, date, included/dropped, and demo/live.

LLM call records include model, prompt version, input hash, output JSON, parsed output, latency, token estimate, cost estimate, and error if a call failed.

## Production Orientation

The POC uses RSS because it is cheap, transparent, and easy to demo without licensed data. But I treated RSS as an adapter, not as the core architecture. The production design is source-agnostic: Bloomberg, Reuters, or internal NBIM feeds would map into the same article schema, then pass through the same rule filter, LLM review, action taxonomy, and audit trail. SQLite proves the audit model locally; Snowflake would become the production audit backend, using the same logical tables with Snowflake-native types and governance. Streamlit can then run inside Snowflake as the review interface, with Snowflake handling access control, secrets, data locality, and auditability.

## Tests

```bash
python3 -m pytest -q
```

The tests cover the action taxonomy, deterministic filtering, demo fallback, and SQLite audit storage.
