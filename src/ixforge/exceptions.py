"""Application exception hierarchy."""

from typing import Any


class IXForgeError(Exception):
    """Base exception for IXForge."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self, message: str = "Internal server error", details: dict[str, Any] | None = None
    ):
        self.message = message
        self.details: dict[str, Any] = details or {}
        super().__init__(message)


class NotFoundError(IXForgeError):
    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, resource: str = "Resource", resource_id: str = ""):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id {resource_id} not found"
        super().__init__(message=message)


class ConflictError(IXForgeError):
    status_code = 409
    error_code = "CONFLICT"

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message=message)


class ValidationError(IXForgeError):
    status_code = 422
    error_code = "VALIDATION_ERROR"

    def __init__(self, message: str = "Validation error", details: dict[str, Any] | None = None):
        super().__init__(message=message, details=details)


class ForbiddenError(IXForgeError):
    status_code = 403
    error_code = "FORBIDDEN"

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message=message)


class UnauthorizedError(IXForgeError):
    status_code = 401
    error_code = "UNAUTHORIZED"

    def __init__(self, message: str = "Not authenticated"):
        super().__init__(message=message)
