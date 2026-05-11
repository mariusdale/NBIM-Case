from pathlib import Path


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"


def test_audit_filter_selected_states_use_digest_button_blue():
    source = APP_SOURCE.read_text()

    assert '[data-testid="stMultiSelect"] [data-baseweb="tag"]' in source
    assert 'div[data-baseweb="calendar"] [aria-selected="true"]' in source
    assert source.count("#005eb8") >= 5


def test_digest_result_does_not_highlight_pipeline_status_as_success():
    source = APP_SOURCE.read_text()

    assert "st.success(result.status_message)" not in source
