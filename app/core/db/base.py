"""Configuration-free declarative registry shared by runtime and migrations."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative Base for all models. (TD-002: id is per-model or mixin)"""
