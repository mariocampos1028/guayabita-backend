from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_template(template_name: str, **context) -> str:
    """Render an HTML email template with the given context."""
    return _env.get_template(template_name).render(**context)
