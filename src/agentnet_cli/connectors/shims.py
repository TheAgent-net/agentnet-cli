"""Load shim templates and discovery context for connector file injection."""

from pathlib import Path

from ..infra.package_paths import bundled_discovery_base

_SHIMS_DIR = Path(__file__).resolve().parent / "templates"
_DISCOVERY_BASE = bundled_discovery_base()


def load_discovery_context() -> str:
    """Return the bundled discovery context text for shim templates."""
    if _DISCOVERY_BASE.is_file():
        return _DISCOVERY_BASE.read_text(encoding="utf-8")
    return (_SHIMS_DIR / "shared" / "context.md").read_text(encoding="utf-8")


def load_shim(relative_path: str) -> str:
    """Load one shim file and inject the discovery context."""
    context = load_discovery_context()
    template = (_SHIMS_DIR / relative_path).read_text(encoding="utf-8")
    return template.replace("{{CONTEXT}}", context)
