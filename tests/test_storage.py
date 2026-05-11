from nbim_digest.actions import ActionCode
from nbim_digest.models import Article, RuleDecision
from nbim_digest.storage import DigestStore


def test_storage_records_audit_row_for_article_decision(tmp_path):
    db_path = tmp_path / "audit.sqlite"
    store = DigestStore(db_path)
    store.initialize()
    run_id = store.create_run(mode="demo", used_cached_outputs=True)
    article = Article(
        title="Oljefondet og porteføljeselskap",
        url="https://example.com/a",
        source="Demo article",
        published_at="2026-05-08",
        description="Portfolio company controversy.",
        discovery_path="Demo article",
        discovery_query=None,
        is_demo=True,
    )
    article_id = store.save_article(run_id, article)
    store.save_rule_decision(
        run_id,
        article_id,
        RuleDecision(
            decision="pass",
            score=100,
            matched_signals=["oljefondet"],
            topic_tags=["ethical exclusions"],
            reason="Direct NBIM/Oil Fund reference.",
        ),
    )
    store.save_digest_decision(
        run_id=run_id,
        article_id=article_id,
        llm_relevance_score=8,
        initial_action=ActionCode.ALERT_COMMUNICATIONS,
        reviewer_action=ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE,
        final_action=ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE,
        included=True,
        reason_for_action="Portfolio company ethics issue needs ownership review.",
        summary="Short summary.",
        recommended_next_step="Forward to Ownership & Compliance before any response.",
        reviewer_skipped=True,
    )

    rows = store.fetch_audit_rows()

    assert len(rows) == 1
    assert rows[0]["article"] == "Oljefondet og porteføljeselskap"
    assert rows[0]["rule_decision"] == "pass"
    assert rows[0]["llm_relevance"] == 8
    assert rows[0]["initial_action"] == "ALERT_COMMUNICATIONS"
    assert rows[0]["reviewer_action"] == "ALERT_OWNERSHIP_AND_COMPLIANCE"
    assert rows[0]["reviewer_skipped"] == 1
    assert rows[0]["final_action"] == "ALERT_OWNERSHIP_AND_COMPLIANCE"
    assert rows[0]["included"] == 1
