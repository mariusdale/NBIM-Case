from pathlib import Path

from nbim_digest.pipeline import DigestPipeline
from nbim_digest.storage import DigestStore


def test_demo_pipeline_uses_cached_outputs_without_api_key(tmp_path):
    store = DigestStore(tmp_path / "demo.sqlite")
    pipeline = DigestPipeline(
        store=store,
        anthropic_api_key=None,
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    result = pipeline.run(mode="demo", use_cached_demo_outputs=True)

    assert result.mode == "demo"
    assert result.used_cached_outputs is True
    assert result.cost.estimated_cost_usd == 0
    assert result.cost.relevance_articles == 0
    assert len(result.items) == 7
    assert {item.final_action.value for item in result.items} >= {
        "MONITOR",
        "ALERT_OWNERSHIP_AND_COMPLIANCE",
        "ESCALATE_TO_LEADERSHIP",
    }
    assert "cached demo outputs" in result.status_message.lower()
