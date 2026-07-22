from agentnet_cli.tools.skillfire import render, steer


def test_steer_reason_omits_agent_section_when_absent():
    # A list-only outcome (no methodology reachable) still gets promoted to final. The steer must
    # not tell the model to follow an AGENT ONLY section that isn't in the payload.
    list_only = render.compose_outcome("AgentNet found these skills:\n\nA — x", "")
    reason = steer.steer_reason(list_only)
    assert render.AGENT_ONLY not in reason
    assert "AGENT ONLY section" not in reason
    assert render.USER_BLOCK_START in reason  # still told to show the list

    fold = steer.fold_context(list_only)
    assert "AGENT ONLY section" not in fold

    # ...but it is referenced when the section really is there.
    full = render.compose_outcome("AgentNet found these skills:\n\nA — x", "read /tmp/SKILL.md")
    assert "AGENT ONLY section" in steer.steer_reason(full)
    assert "AGENT ONLY section" in steer.fold_context(full)
