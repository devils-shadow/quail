from __future__ import annotations

from pathlib import Path


def test_css_bundle_matches_partials() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    styles_dir = repo_root / "quail" / "templates" / "partials" / "styles"
    bundle_path = repo_root / "quail" / "static" / "quail.css"
    parts = [
        styles_dir / "01-theme.css",
        styles_dir / "02-shell.css",
        styles_dir / "03-page.css",
        styles_dir / "04-admin-components.css",
        styles_dir / "05-inbox-message.css",
        styles_dir / "06-responsive.css",
    ]

    missing = [path for path in parts if not path.exists()]
    assert not missing, f"Missing CSS partials: {missing}"
    assert bundle_path.exists(), "Missing CSS bundle. Run `make css-bundle`."

    expected = "".join(path.read_text(encoding="utf-8") for path in parts)
    actual = bundle_path.read_text(encoding="utf-8")
    assert actual == expected, "CSS bundle is stale. Run `make css-bundle`."
