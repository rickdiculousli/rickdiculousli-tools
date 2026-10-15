"""Delegation evidence tooling: overlay parsing, tree hashing and the ledger."""


class DelegationError(Exception):
    """A refused operation or an environment problem (CLI exit code 2)."""
