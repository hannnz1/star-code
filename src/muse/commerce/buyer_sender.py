"""Fixed synthetic Store API purchase on an owned disposable reference site.

No public tool or passed-report endpoint. Checkout UNKNOWN is committed before
POST, and read-only recovery never creates another cart/order. Browser evidence
and the final nine-check report remain separate from this order readback.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import re
from decimal import Decimal

import httpx

from muse.commerce.buyer_probe import BuyerSource
from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.reference_jobs import ReferenceJobRepository
from muse.commerce.repository import digest
from muse.commerce.staging_source import StagingSourceRepository

ADDRESS = {'first_name': 'MUSE', 'last_name': 'Probe', 'company': '', 'address_1': '1 Fixture Street',
    'address_2': '', 'city': 'Beverly Hills', 'state': 'CA', 'postcode': '90210', 'country': 'US'}
BILLING = {**ADDRESS, 'email': 'muse-probe@example.invalid', 'phone': '0000000000'}


class SyntheticBuyer:
    def __init__(self, probes, jobs, runner, sources, *, transport=None):
        if not isinstance(sources, StagingSourceRepository) or sources.db is not probes.db or jobs.db is not probes.db:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        self.probes, self.jobs, self.runner, self.sources, self.transport = probes, jobs, runner, sources, transport

    def _target(self, project_id, job_id):
        validate_lock(self.runner.lock)
        job = self.jobs.read(project_id, job_id)
        if job.state != 'READY':
            raise CommerceFailure('VERIFICATION_UNAVAILABLE', 503)
        connection = self.runner._connection(job)
        if (connection.environment != 'staging' or connection.project_id != project_id
                or connection.connection_id != 'ref-' + job_id
                or connection.base_url != 'http://127.0.0.1:' + str(job.port)):
            raise CommerceFailure('PERMISSION_DENIED', 403)
        return job, connection

    def _authorize(self, conn, project_id, plan_id, job_id, grant_id, sku, connection, *, include_delivery=False):
        job = ReferenceJobRepository._read(conn, project_id, job_id)
        if job.state != 'READY':
            raise CommerceFailure('REVIEW_STALE')
        intent, history = self.sources._verification_source(conn, grant_id, connection, fresh=True)
        if (intent.project_id != project_id or intent.plan_id != plan_id
                or intent.target.connector_ref != connection.connection_id or not history):
            raise CommerceFailure('REVIEW_STALE')
        fixture = None
        candidates = [product for product in intent.products if product.sku == sku]
        if not candidates and not any(product.stock >= 1 for product in intent.products):
            from muse.commerce.buyer_fixture import BuyerFixtureRepository
            from muse.commerce.verification_jobs import VerificationJobRepository
            fixture = BuyerFixtureRepository.read(conn, VerificationJobRepository(self.probes.repo),
                project_id, plan_id, job_id, intent)
            if fixture.draft.sku == sku: candidates = [fixture.draft]
        actual = [product for product in history[-1].snapshot.products if product.get('sku') == sku]
        if (len(candidates) != 1 or candidates[0].stock < 1 or len(actual) != 1
                or type(actual[0].get('id')) is not int or actual[0]['id'] <= 0
                or fixture is not None and actual[0]['id'] != fixture.product_id):
            raise CommerceFailure('VERIFICATION_FAILED', 422)
        source = BuyerSource(job_id=job_id, source_digest=intent.source_digest, staging_intent_digest=intent.digest,
            product_id=actual[0]['id'], sku=sku, connection_id=connection.connection_id)
        if include_delivery:
            delivery,address=self._delivery(intent,history[-1].snapshot,candidates[0])
            return source,candidates[0],delivery,address
        return source, candidates[0]

    @staticmethod
    def _delivery(intent,snapshot,product):
        blueprint=getattr(intent,'blueprint',None)
        raw=blueprint.required_settings.get('shipping_rules') if blueprint else None
        if raw is None:
            return None,dict(ADDRESS)
        try:
            from muse.commerce.shipping_rules import ShippingRules
            from muse.commerce.store_configuration import shipping_effect
            rules=ShippingRules.model_validate(raw)
            actual=snapshot.settings.get('shipping_configuration')
            shipping_effect(actual,actual,intent.project_id,raw)
            # Fixed synthetic addresses, never merchant/customer personal data.
            fixtures={'US':('CA','90210','Beverly Hills'),'AU':('NSW','2000','Sydney'),
                'GB':('','SW1A 1AA','London'),'CA':('ON','M5V 3L9','Toronto'),
                'DE':('','10115','Berlin'),'FR':('','75001','Paris'),'JP':('JP13','100-0001','Tokyo')}
            country=next((code for zone in rules.zones for code in zone.countries if code in fixtures),None)
            if country is None:
                raise CommerceFailure('UNSUPPORTED_CAPABILITY',422)
            amount=rules.quote(country,product.price)
            zone=next(zone for zone in actual['zones'] if country in zone['countries'])
            approved_zone=next(zone for zone in rules.zones if country in zone.countries)
            kind='free_shipping' if approved_zone.free_from is not None and product.price>=Decimal(approved_zone.free_from) else 'flat_rate'
            method=next(method for method in zone['methods'] if method['method_id']==kind)
            state,postcode,city=fixtures[country]
            address={**ADDRESS,'country':country,'state':state,'postcode':postcode,'city':city}
            return {'method_id':kind,'rate_id':kind+':'+str(method['instance_id']),'amount':amount,'currency':rules.currency},address
        except (ValueError,TypeError,KeyError,StopIteration,AttributeError):
            raise CommerceFailure('VERIFICATION_FAILED',422) from None

    async def _request(self, client, connection, method, path, *, body=None, headers=None, params=None, authenticated=False):
        allowed = {'/muse-staging/v1/safety', '/muse-staging/v1/disposable-product', '/muse-staging/v1/probe-order', '/wc/store/v1/cart',
            '/wc/store/v1/cart/add-item', '/wc/store/v1/cart/update-customer',
            '/wc/store/v1/cart/select-shipping-rate', '/wc/store/v1/checkout'}
        if path not in allowed or method not in {'GET', 'POST'}:
            raise CommerceFailure('PERMISSION_DENIED', 403)
        if authenticated != (path.startswith('/muse-staging/')) or authenticated and method != 'GET':
            raise CommerceFailure('PERMISSION_DENIED', 403)
        try:
            async with client.stream(method, connection.base_url + '/wp-json' + path,
                    json=body, headers=headers, params=params,
                    auth=(connection.username, connection.application_password) if authenticated else None) as response:
                statuses = {200, 201} if method == 'POST' and path in {'/wc/store/v1/cart/add-item', '/wc/store/v1/checkout'} else {200}
                if response.status_code not in statuses or response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    raise CommerceFailure('VERIFICATION_FAILED', 422)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 256 * 1024:
                        raise CommerceFailure('VERIFICATION_FAILED', 422)
                value = json.loads(data)
                if not isinstance(value, dict):
                    raise TypeError()
                return value, response.headers.get('Cart-Token')
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, UnicodeError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN' if method == 'POST' else 'READ_TEMPORARY_FAILURE', 503) from None

    async def _safety(self, client, job, connection):
        value, _ = await self._request(client, connection, 'GET', '/muse-staging/v1/safety', authenticated=True)
        if (value.get('job_id') != job.id or value.get('environment') != 'staging'
                or value.get('wordpress_version') != self.runner.lock['wordpress']
                or value.get('woocommerce_version') != self.runner.lock['woocommerce']
                or any(value.get(key) is not True for key in ('email_disabled', 'external_requests_disabled',
                    'indexing_disabled', 'cron_disabled', 'offline_gateway_only'))):
            raise CommerceFailure('VERIFICATION_FAILED', 422)

    async def disposable_product(self, project_id, job_id, *, currency):
        """Read a fixed hidden product from this owned READY job, never create."""
        from muse.commerce.buyer_fixture import read_disposable_product
        job, connection = self._target(project_id, job_id)
        async with (
            asyncio.timeout(45),
            httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=20,
                headers={'Accept-Encoding': 'identity'}) as client,
        ):
            await self._safety(client, job, connection)
            raw, _ = await self._request(client, connection, 'GET', '/muse-staging/v1/disposable-product', authenticated=True)
            product = read_disposable_product(raw, project_id=project_id, job_id=job_id, currency=currency)
            current, target = self._target(project_id, job_id)
            if current != job or target != connection:
                raise CommerceFailure('REVIEW_STALE')
            return product

    @staticmethod
    def _cart(value, source, product):
        try:
            items = value['items']
            if not isinstance(items, list) or len(items) != 1:
                raise ValueError()
            item = items[0]
            prices = item['prices']
            minor = prices['currency_minor_unit']
            price = prices['price']
            if (type(item['id']) is not int or item['id'] != source.product_id or item['sku'] != source.sku
                    or type(item['quantity']) is not int or item['quantity'] != 1 or type(minor) is not int
                    or not 0 <= minor <= 6 or not isinstance(price, str) or not re.fullmatch(r'[0-9]{1,18}', price)
                    or prices['currency_code'] != product.currency
                    or Decimal(price) / (Decimal(10) ** minor) != product.price):
                raise ValueError()
        except (ValueError, TypeError, KeyError, ArithmeticError):
            raise CommerceFailure('VERIFICATION_FAILED', 422) from None

    async def send(self, project_id, plan_id, job_id, grant_id, sku):
        try:
            return await self._send(project_id, plan_id, job_id, grant_id, sku)
        except (TimeoutError, OSError, ValueError, TypeError, KeyError, AttributeError):
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN', 503) from None

    async def _send(self, project_id, plan_id, job_id, grant_id, sku):
        identity = digest([project_id, plan_id, 'buyer_probe', job_id])
        try:
            self.probes.read(project_id, plan_id, identity)
        except CommerceFailure as error:
            if error.public.code != 'NOT_FOUND':
                raise
        else:
            raise CommerceFailure('WRITE_OUTCOME_UNKNOWN')
        job, connection = self._target(project_id, job_id)
        with self.probes.db.transaction() as conn:
            source, product, delivery, address = self._authorize(conn, project_id, plan_id, job_id, grant_id, sku, connection,include_delivery=True)
        billing={**address,'email':BILLING['email'],'phone':BILLING['phone']}
        private = self.runner._read_private(job, 'connection.json')
        secret = private.get('execution_secret')
        if not isinstance(secret, str) or not 32 <= len(secret) <= 256:
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        async with (
            asyncio.timeout(180),
            httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=20,
                headers={'Accept-Encoding': 'identity'}) as client,
        ):
            await self._safety(client, job, connection)
            cart, token = await self._request(client, connection, 'GET', '/wc/store/v1/cart')
            if (cart.get('items') != [] or not isinstance(token, str)
                    or not re.fullmatch(r'[a-zA-Z0-9_.-]{16,8192}', token)):
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            headers = {'Cart-Token': token}
            cart, _ = await self._request(client, connection, 'POST', '/wc/store/v1/cart/add-item',
                body={'id': source.product_id, 'quantity': 1}, headers=headers)
            self._cart(cart, source, product)
            cart, _ = await self._request(client, connection, 'POST', '/wc/store/v1/cart/update-customer',
                body={'billing_address': billing, 'shipping_address': address}, headers=headers)
            self._cart(cart, source, product)
            packages = cart.get('shipping_rates')
            if not isinstance(packages, list) or len(packages) != 1:
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            package = packages[0]
            if not isinstance(package, dict):
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            rates = package.get('shipping_rates')
            if (type(package.get('package_id')) is not int or not isinstance(rates, list) or len(rates) != 1
                    or not isinstance(rates[0], dict) or rates[0].get('method_id') != (delivery['method_id'] if delivery else 'flat_rate')
                    or not isinstance(rates[0].get('rate_id'), str)
                    or not re.fullmatch(r'(?:flat_rate|free_shipping):[1-9][0-9]{0,9}', rates[0].get('rate_id', ''))):
                raise CommerceFailure('VERIFICATION_FAILED', 422)
            if delivery and (rates[0]['rate_id']!=delivery['rate_id'] or rates[0].get('currency_code')!=delivery['currency']
                or type(rates[0].get('currency_minor_unit')) is not int or rates[0]['currency_minor_unit']!=2
                or not isinstance(rates[0].get('price'),str) or not re.fullmatch(r'[0-9]{1,18}',rates[0]['price'])
                or Decimal(rates[0]['price'])/100!=delivery['amount']):
                raise CommerceFailure('VERIFICATION_FAILED',422)
            cart, _ = await self._request(client, connection, 'POST', '/wc/store/v1/cart/select-shipping-rate',
                body={'package_id': package['package_id'], 'rate_id': rates[0]['rate_id']}, headers=headers)
            self._cart(cart, source, product)
            # Source/cancellation/expiry/READY are checked in the same DB
            # transaction as the durable send fence, after all cart preparation.
            def authorize(conn):
                current, draft = self._authorize(conn, project_id, plan_id, job_id, grant_id, sku, connection)
                if draft != product:
                    raise CommerceFailure('REVIEW_STALE')
                return current
            await self._safety(client, job, connection)
            probe = self.probes.begin(project_id, plan_id, source, authorize=authorize, expected_product=product,
                expected_shipping=delivery['amount'] if delivery else None)
            payload = base64.b64encode(json.dumps({'job_id': job_id, 'probe_id': probe.id,
                'source_digest': source.source_digest, 'staging_intent_digest': source.staging_intent_digest,
                'product_id': source.product_id, 'sku': source.sku}, separators=(',', ':')).encode()).decode()
            checkout_headers = {**headers, 'X-Muse-Probe': payload,
                'X-Muse-Probe-Signature': hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()}
            reply, _ = await self._request(client, connection, 'POST', '/wc/store/v1/checkout', headers=checkout_headers,
                body={'billing_address': billing, 'shipping_address': address, 'payment_method': 'cod',
                    'payment_data': [], 'customer_note': ''})
            # Discard all customer/session/order-key fields in the raw response.
            self.probes.complete(probe.id, {'order_id': reply.get('order_id'), 'status': reply.get('status')})
            proof, _ = await self._request(client, connection, 'GET', '/muse-staging/v1/probe-order',
                params={'probe_id': probe.id}, authenticated=True)
            return self.probes.confirm_readback(probe.id, proof, require_amounts=True)

    async def reconcile(self, project_id, plan_id, identity):
        try:
            return await self._reconcile(project_id, plan_id, identity)
        except (TimeoutError, OSError, ValueError, TypeError, KeyError, AttributeError):
            raise CommerceFailure('READ_TEMPORARY_FAILURE', 503) from None

    async def _reconcile(self, project_id, plan_id, identity):
        probe = self.probes.read(project_id, plan_id, identity)
        job, connection = self._target(project_id, probe.source.job_id)
        if probe.source.connection_id != connection.connection_id:
            raise CommerceFailure('PERMISSION_DENIED', 403)
        async with (
            asyncio.timeout(45),
            httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=20,
                headers={'Accept-Encoding': 'identity'}) as client,
        ):
            await self._safety(client, job, connection)
            proof, _ = await self._request(client, connection, 'GET', '/muse-staging/v1/probe-order',
                params={'probe_id': identity}, authenticated=True)
            return self.probes.confirm_readback(identity, proof, require_amounts=True)
