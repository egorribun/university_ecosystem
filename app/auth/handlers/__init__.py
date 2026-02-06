"""Auth handlers package.

This package contains extracted handlers from auth.py following
the Single Responsibility Principle.
"""

from .logout import router as logout_router

__all__ = ["logout_router"]
