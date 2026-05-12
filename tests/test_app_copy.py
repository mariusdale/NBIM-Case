import ast
from pathlib import Path


APP_SOURCE = Path("app.py").read_text()


def _function_node(name: str) -> ast.FunctionDef:
    module = ast.parse(APP_SOURCE)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name} was not found")


def test_digest_landing_copy_does_not_show_demo_api_key_prompt():
    assert "Run the demo digest to see the full pipeline without API keys." not in APP_SOURCE


def test_digest_page_defines_time_horizon_for_pipeline_run():
    digest_page = _function_node("digest_page")

    assigns_time_horizon = any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "time_horizon" for target in node.targets)
        for node in ast.walk(digest_page)
    )

    assert assigns_time_horizon


def test_digest_feedback_controls_use_blue_interaction_states():
    assert 'div[data-testid="stExpander"] details summary:hover' in APP_SOURCE
    assert 'div[data-testid="stExpander"] details summary {' in APP_SOURCE
    assert 'div[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within' in APP_SOURCE
    assert 'div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within' in APP_SOURCE
    assert 'div[data-testid="stButton"] button:active' in APP_SOURCE
