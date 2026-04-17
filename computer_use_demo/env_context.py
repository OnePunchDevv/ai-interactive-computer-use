import os
from contextvars import ContextVar

# This ContextVar holds task-local environment overrides (like DISPLAY, WIDTH, HEIGHT)
# so concurrent agents don't corrupt each other's environment variables.
session_env: ContextVar[dict[str, str] | None] = ContextVar("session_env", default=None)


def get_session_env() -> dict[str, str]:
    """Return the merged environment dictionary."""
    env = os.environ.copy()
    overrides = session_env.get()
    if overrides:
        env.update(overrides)
    return env


def get_session_env_var(key: str, default: str | None = None) -> str | None:
    """Get a variable from the session context, falling back to os.environ."""
    overrides = session_env.get()
    if overrides and key in overrides:
        return overrides[key]
    return os.getenv(key, default)
