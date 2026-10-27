"""Public-key-only platform assertion verification and guards."""
from .verify import AssertionVerifier, AssertionError401

__all__ = ['AssertionVerifier', 'AssertionError401']
