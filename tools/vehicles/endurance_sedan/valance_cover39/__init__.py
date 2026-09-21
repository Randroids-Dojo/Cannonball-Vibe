"""Finite current-input rear cover; caller owns source capture and persistence."""
from .api import prepare
from .preview import apply
from .native import apply as install
from .profile import finite_domains
from .reference import triangle_domains

__all__ = ["prepare", "apply", "install", "finite_domains", "triangle_domains"]
