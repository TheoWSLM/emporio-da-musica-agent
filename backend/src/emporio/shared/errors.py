"""Domain-level errors. Tools translate them into structured results for the model."""


class DomainError(Exception):
    """A business rule prevented the operation."""


class NotFoundError(DomainError):
    """The requested entity does not exist."""
