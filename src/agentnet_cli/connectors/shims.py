from pathlib import Path

from ..infra.package_paths import bundled_discovery_base

_SHIMS_DIR = Path(__file__).resolve().parent / "templates"
_DISCOVERY_BASE = bundled_discovery_base()


def load_discovery_context() -> str:
    if _DISCOVERY_BASE.is_file():
        return _DISCOVERY_BASE.read_text()
    return (_SHIMS_DIR / "shared" / "context.md").read_text()


def load_shim(relative_path: str) -> str:
    context = load_discovery_context()
    template = (_SHIMS_DIR / relative_path).read_text()
    return template.replace("{{CONTEXT}}", context)
