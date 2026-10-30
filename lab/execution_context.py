"""Task-local transport identity for the unchanged official SDK invocation."""
from contextvars import ContextVar

grant = ContextVar("execution_grant", default=None)
