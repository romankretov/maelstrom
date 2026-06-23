"""Test fixtures and env setup.

Sets dummy env vars before any maelstrom_api imports happen, so Settings
(which has no defaults for these) doesn't raise during test collection.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_SECRET_KEY", "test-secret-please-rotate")
os.environ.setdefault("MAELSTROM_ENV", "development")
