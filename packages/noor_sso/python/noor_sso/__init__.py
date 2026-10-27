"""Public-key-only platform assertion verification and guards."""
from .verify import AssertionError401, AssertionVerifier

__all__ = ['AssertionVerifier', 'AssertionError401']
