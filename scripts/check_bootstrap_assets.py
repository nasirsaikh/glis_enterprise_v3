"""Check the framework boundary without installing a frontend build toolchain."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for name in ("css/bootstrap.min.css", "css/bootstrap.rtl.min.css", "js/bootstrap.bundle.min.js"):
    path = ROOT / "static" / name
    assert re.search(r"Bootstrap\s+v5\.3\.2\b", path.read_text()[:500]), f"Unexpected Bootstrap version: {name}"
for name in ("css/bootstrap-layout.css", "css/style.css", "js/main.js"):
    assert (ROOT / "static" / name).stat().st_size > 0, f"Missing asset: {name}"

obsolete = re.compile(r"(?<![\w-])(?:(?:sm|md|lg|xl):[\w\[]|(?:grid-cols-|col-span-|glis-[wh]-100|bg-base-|text-base-content|w-full|h-full|modal-box|modal-action|dropdown-content|input-bordered|select-bordered|textarea-bordered|checkbox-primary|radio-primary|toggle-primary|badge-primary|badge-error|btn-ghost|tabs-lift|tabs-box|steps-horizontal|steps-vertical|step-primary)|\[&_[^]]+\]:|tw:)")
sources = [*ROOT.joinpath("templates").rglob("*.html"), *ROOT.joinpath("static/js").glob("*.js"),
           *ROOT.joinpath("apps").glob("*/forms.py"), ROOT / "apps/accounts/views.py", ROOT / "services/dynamic_forms.py"]
errors = []
for path in sources:
    if path.name.startswith("bootstrap"): continue
    text = path.read_text()
    if match := obsolete.search(text): errors.append(f"{path.relative_to(ROOT)}: {match[0]}")
    if "showModal(" in text or "<dialog" in text: errors.append(f"{path.relative_to(ROOT)}: obsolete dialog lifecycle")
for base in ("base_portal.html", "base_public.html"):
    text = (ROOT / "templates" / base).read_text()
    for required in ('components/bootstrap_styles.html', "css/style.css", "js/bootstrap.bundle.min.js", "js/main.js"):
        if required not in text: errors.append(f"{base}: missing {required}")
    if "output.css" in text or "bootstrap-compat" in text: errors.append(f"{base}: obsolete stylesheet")
if errors: raise SystemExit("\n".join(errors))
print(f"Bootstrap 5.3.2 assets and {len(sources)} UI source files verified.")
