from pathlib import Path

_SHIMS_DIR = Path(__file__).resolve().parent.parent / "shims"


def load_shim(relative_path: str) -> str:
    context = (_SHIMS_DIR / "shared" / "context.md").read_text()
    template = (_SHIMS_DIR / relative_path).read_text()
    return template.replace("{{CONTEXT}}", context)
