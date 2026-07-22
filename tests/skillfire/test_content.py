import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentnet_cli.tools.skillfire import content


def _use_output(download_dir, *, name="launchdarkly-flag-create", desc=None):
    """`skills use` stdout pointing at ``download_dir``.

    The dir must really exist — `summarize_skill` verifies the SKILL.md is on disk before
    claiming it (see test_summarize_skill_rejects_nonexistent_path).
    """
    desc = desc if desc is not None else '"Create and configure LaunchDarkly feature flags."'
    return (
        "You are being given a Skill to execute for the user's next request.\n\n"
        "Use the following SKILL.md as your instructions:\n\n"
        "<SKILL.md>\n"
        "---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# LaunchDarkly Flag Create\n\nlong methodology body...\n"
        "</SKILL.md>\n\n"
        "Supporting files for this skill were downloaded to:\n"
        f"{download_dir}\n\n"
        "When the SKILL.md references relative paths, read them from that directory.\n"
    )


def _real_skill_dir(tmp_path, name="launchdarkly-flag-create"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("# on disk\n")
    return d


# ── summarize_skill (condense `skills use` output to header + on-disk path) ──
def test_summarize_skill_with_references(tmp_path):
    # Skill downloaded a dir (has references) -> point at that dir's SKILL.md, don't dump the body.
    d = _real_skill_dir(tmp_path)
    out = content.summarize_skill(
        _use_output(d), slug="launchdarkly-flag-create", desc_hint="x"
    )
    assert out.startswith("launchdarkly-flag-create — Create and configure LaunchDarkly")
    assert f"{d}/SKILL.md" in out
    assert "Read it and follow it" in out
    assert "long methodology body" not in out  # the full SKILL.md is NOT dumped in


def test_summarize_skill_single_file():
    # No download path -> materialize the printed body to a temp SKILL.md we point at.
    raw = "<SKILL.md>\n---\nname: solo\ndescription: does solo\n---\n# body\nstuff\n</SKILL.md>\n"
    out = content.summarize_skill(raw, slug="solo", desc_hint="")
    assert out.startswith("solo — does solo")
    m = re.search(r"(\S+/SKILL\.md)", out)
    assert m and Path(m.group(1)).read_text().strip().endswith("stuff")  # body on disk
    assert "# body" not in out.split("on disk")[0]  # body not inlined into the header


def test_summarize_skill_reads_yaml_block_scalar_description(tmp_path):
    # Regression: `description: >` (and `|`) put the text on following indented lines. A line-regex
    # captured only the marker, so the injected list read "progress-report — >".
    d = _real_skill_dir(tmp_path, name="progress-report")
    raw = (
        "<SKILL.md>\n"
        "---\n"
        "name: progress-report\n"
        "description: >\n"
        "  Displays progress dashboard showing phase completion, blocked tasks,\n"
        "  and remaining work estimate.\n"
        "version: 0.0.1\n"
        "---\n"
        "body\n"
        "</SKILL.md>\n"
        f"Supporting files for this skill were downloaded to:\n{d}\n"
    )
    header = content.summarize_skill(raw, slug="progress-report", desc_hint="").splitlines()[0]
    assert header.startswith("progress-report — Displays progress dashboard")
    assert ">" not in header


def test_summarize_skill_unparseable():
    assert content.summarize_skill("no <skill> block here", slug="x", desc_hint="") == ""


def test_summarize_skill_rejects_nonexistent_path():
    # Regression: we claimed a SKILL.md was "on disk" without checking. The agent hunted for the
    # file, failed, and abandoned the skill ("path wasn't on disk, so I built it manually").
    raw = (
        "<SKILL.md>\n---\nname: ghost\ndescription: d\n---\nbody\n</SKILL.md>\n"
        "Supporting files for this skill were downloaded to:\n/nonexistent/ghost-skill-dir\n"
    )
    assert content.summarize_skill(raw, slug="ghost", desc_hint="") == ""


def test_summarize_skill_caps_description(tmp_path):
    d = _real_skill_dir(tmp_path, name="s")
    raw = _use_output(d, name="s", desc="d" * 500)
    header = content.summarize_skill(raw, slug="s", desc_hint="").splitlines()[0]
    assert header.endswith("…") and len(header) <= content._DESC_CAP + len("s — ")


# ── skill_content (npx skills use <repo>@<slug> -> concise header, no install) ─
def test_skill_content(tmp_path):
    d = _real_skill_dir(tmp_path)
    with (
        patch("agentnet_cli.tools.skillfire.content.shutil.which",
              side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.skillfire.content.subprocess.run",
              return_value=MagicMock(returncode=0, stdout=_use_output(d))) as run,
    ):
        out = content.skill_content(
            "ld/agent", "launchdarkly-flag-create", desc_hint="x", timeout=5
        )
    assert "launchdarkly-flag-create — Create and configure" in out
    assert str(d) in out
    cmd = run.call_args.args[0]
    assert cmd[1:] == ["-y", "skills", "use", "ld/agent@launchdarkly-flag-create"]


def _with_npx(run_result):
    return (
        patch("agentnet_cli.tools.skillfire.content.shutil.which",
              side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.skillfire.content.subprocess.run", return_value=run_result),
    )


def test_skill_content_best_effort():
    with patch("agentnet_cli.tools.skillfire.content.shutil.which", return_value=None):
        assert content.skill_content("r/foo", "Foo", desc_hint="", timeout=5) == ""  # no npx
    a, b = _with_npx(MagicMock(returncode=1, stdout=""))
    with a, b:
        assert content.skill_content("r/foo", "Foo", desc_hint="", timeout=5) == ""  # exit 1
    a, b = _with_npx(MagicMock(returncode=0, stdout="No matching skill found for: x"))
    with a, b:
        assert content.skill_content("r/foo", "Foo", desc_hint="", timeout=5) == ""  # listing
