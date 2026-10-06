"""Module renderers."""

from html import escape


def render_module(module: dict, derived) -> str:
    title = module.get("title", module["type"].capitalize())
    return (f'<section class="module" id="{module["anchor"]}" data-type="{module["type"]}">'
            f'<h2>{escape(title)}</h2></section>')
