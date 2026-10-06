"""Default-disabled website broker with the shared durable send/recovery path.

Execution requires a verified Linux lock and current private merchant approval
backed by trusted evidence. This module opens no public write route.
"""
import asyncio

from muse.commerce.context import normalize_snapshot
from muse.commerce.errors import CommerceFailure
from muse.commerce.site_steps import CompletedSiteStep
from muse.commerce_connector.release_publisher import ProductReleasePublisher
from muse.commerce_connector.wordpress import WordPressReader


class SiteReleasePublisher(ProductReleasePublisher):
    maximum_read_seconds = 60
    required_operations = frozenset({'install_theme_package', 'create_owned_page', 'publish_owned_page',
        'set_storefront_options', 'set_owned_navigation', 'create_product_draft', 'publish_product'})
    completed_type = CompletedSiteStep

    async def _read_context(self, intent):
        reader = WordPressReader(self.connection, transport=self.transport)
        try:
            async with asyncio.timeout(self.maximum_read_seconds):
                raw = await reader.read('snapshot', remaining_seconds=20)
                snapshot = normalize_snapshot(raw, self.connection.project_id, self.connection.environment)
                proofs = {}
                for step in intent.steps:
                    if step.kind == 'create_owned_media':
                        proof = await reader.read_media_sha256(step.payload['image']['sha256'], remaining_seconds=20)
                    elif step.kind == 'create_owned_page':
                        proof = await reader.read_page_slug(step.payload['slug'], remaining_seconds=20)
                    elif step.kind == 'create_product_draft':
                        proof = await reader.read_sku(step.payload['product']['sku'], remaining_seconds=20)
                    else:
                        continue
                    if proof['resource_key'] != step.resource_ref:
                        raise CommerceFailure('REVIEW_STALE')
                    proofs[step.resource_ref] = proof
                return snapshot, proofs
        except TimeoutError:
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 502) from None

    async def _issue_permit(self, execution, attempt, history, snapshot, proofs):
        code = await self._store(self.journal.frozen_code, attempt.grant_id, self.connection)
        return self.authority.issue(execution.grant, execution.intent, self.connection, code,
                                    attempt.index, history, snapshot, proofs)

    async def _check_permit(self, token, execution, attempt, history, snapshot, proofs):
        code = await self._store(self.journal.frozen_code, attempt.grant_id, self.connection)
        return self.authority.verify(token, execution.grant, execution.intent, self.connection, code,
                                     attempt.index, history, snapshot, proofs)
