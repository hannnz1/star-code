from typing import Protocol

from muse.commerce.errors import CommerceFailure
from muse.commerce.models import EnvironmentRef, PlatformCapabilities, StoreSnapshot


class CommercePlatform(Protocol):
    async def describe(self, project_id: str, connection_id: str) -> EnvironmentRef: ...
    async def capabilities(self, project_id: str, connection_id: str) -> PlatformCapabilities: ...
    async def snapshot(self, project_id: str, connection_id: str, environment: str) -> StoreSnapshot: ...


class UnconfiguredPlatform:
    async def describe(self, project_id, connection_id):
        raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503, project_id=project_id)

    async def capabilities(self, project_id, connection_id):
        raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503, project_id=project_id)

    async def snapshot(self, project_id, connection_id, environment):
        raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503, project_id=project_id)
