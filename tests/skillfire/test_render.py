from agentnet_cli.tools.skillfire import render


# ── render_list (the AgentNet recommendation list: name + why + link) ─────────
def test_render_list():
    # `name (NN%) — description` only. No install commands (agents executed them) and no URLs —
    # this block is meant to be reproduced to the user verbatim.
    skills = {"A": {"url": "http://a", "repo": "r/a", "install_cmd": "npx add", "score": "88.6"}}
    out = render.render_list([{"name": "A", "why": "helps"}], skills, limit=5)
    assert out == "AgentNet found these skills:\n\nA (89%) — helps"
    assert "install" not in out and "http://a" not in out
    # no score -> no percentage
    assert render.render_list([{"name": "A", "why": "w"}], {}, limit=5).endswith("A — w")
    assert render.render_list([], {}, limit=5) == ""  # nothing relevant -> ""


def test_render_list_respects_limit():
    rel = [{"name": f"S{i}", "why": "w"} for i in range(5)]
    out = render.render_list(rel, {}, limit=2)
    assert len([ln for ln in out.splitlines() if ln.startswith("S")]) == 2


def test_compose_outcome():
    # The user-facing list is fenced apart from the agent-only path instruction, otherwise the
    # agent collapses the whole thing into "AgentNet found a relevant skill, let me read it".
    out = render.compose_outcome("LIST", "CONTENT")
    assert render.USER_BLOCK_START in out and render.USER_BLOCK_END in out
    assert render.AGENT_ONLY in out
    assert "Reading the top match and applying it." in out
    assert out.index("LIST") < out.index(render.USER_BLOCK_END) < out.index("CONTENT")

    # list only -> fenced user block, no agent section to leak
    only = render.compose_outcome("LIST", "")
    assert "LIST" in only and render.AGENT_ONLY not in only
    assert render.compose_outcome("", "CONTENT") == "CONTENT"
