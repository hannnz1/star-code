"""Public business failures never expose connector credentials or input paths."""
from typing import Any, Literal

from pydantic import BaseModel, Field

ErrorCode = Literal['NOT_FOUND', 'INPUT_INVALID', 'FACTS_INCOMPLETE', 'AUTH_REQUIRED', 'PERMISSION_DENIED',
                    'UNSUPPORTED_CAPABILITY', 'RESOURCE_CONFLICT', 'REVIEW_STALE', 'APPROVAL_REQUIRED',
                    'APPROVAL_EXPIRED', 'READ_TEMPORARY_FAILURE', 'MODEL_UNAVAILABLE', 'BUDGET_EXHAUSTED',
                    'MODEL_OUTPUT_INVALID', 'VERIFICATION_FAILED', 'VERIFICATION_UNAVAILABLE',
                    'WRITE_OUTCOME_UNKNOWN', 'PARTIAL_APPLY', 'EXECUTION_BOUNDARY_UNAVAILABLE',
                    'CANCELLED_WITH_INFLIGHT', 'PROJECT_BUSY', 'PROJECT_ARCHIVED']


class CommerceError(BaseModel):
    code: ErrorCode
    message: str
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False
    next_action: str
    project_id: str | None = None
    plan_id: str | None = None
    operation_id: str | None = None


class CommerceErrorEnvelope(BaseModel):
    error: CommerceError


class CommerceFailure(Exception):
    def __init__(self, code: ErrorCode, status: int = 409, *, project_id: str | None = None):
        messages = {
            'PROJECT_BUSY': ('The project has active tasks, unresolved writes or an environment requiring cleanup.', 'Stop active tasks, reconcile results and clean up preview environments before removing the project.'),
            'PROJECT_ARCHIVED': ('This project is archived.', 'Restore the project in Settings before continuing.'),
            'NOT_FOUND': ('The requested commerce resource was not found.', 'Select an existing project.'),
            'RESOURCE_CONFLICT': ('The resource has changed.', 'Refresh and review the current revision.'),
            'INPUT_INVALID': ('The input is invalid.', 'Correct the indicated fields.'),
            'APPROVAL_REQUIRED': ('A current merchant approval is required.', 'Review the changes before publishing.'),
            'UNSUPPORTED_CAPABILITY': ('The requested capability is not available.', 'Use the supported platform and scope.'),
            'MODEL_UNAVAILABLE': ('The configured model is unavailable.', 'Restore the configured model before continuing.'),
            'AUTH_REQUIRED': ('The store connection requires authentication.', 'Reconnect using a valid service identity.'),
            'PERMISSION_DENIED': ('The store connection does not allow this request.', 'Review the configured target and permissions.'),
            'READ_TEMPORARY_FAILURE': ('The store could not be read within the allowed time.', 'Restore the connection and explicitly resume.'),
            'VERIFICATION_UNAVAILABLE': ('The required service is not configured.', 'Configure and verify the independent commerce environment.'),
            'EXECUTION_BOUNDARY_UNAVAILABLE': ('The required isolated execution environment is unavailable.', 'Verify the Linux execution boundary before proceeding.'),
        }
        message, action = messages.get(code, ('The operation could not be completed.', 'Review the project status.'))
        self.status = status
        self.public = CommerceError(code=code, message=message, next_action=action, project_id=project_id)
        super().__init__(message)
