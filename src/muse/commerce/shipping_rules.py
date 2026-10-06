"""Frozen, bounded shipping intent. Saving it never configures a remote store."""
from decimal import Decimal
import re

from pydantic import Field, field_validator, model_validator

from muse.commerce.models import Contract

# ISO 3166-1 alpha-2; no invented worldwide fallback or subdivision matching.
COUNTRIES = frozenset('AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'.split())


class ShippingZone(Contract):
    key: str = Field(pattern=r'^[a-z][a-z0-9-]{0,39}$')
    name: str = Field(min_length=1, max_length=100, pattern=r'^[^<>\x00]+$')
    countries: list[str] = Field(min_length=1, max_length=20)
    rate: str
    free_from: str | None = None

    @field_validator('name')
    @classmethod
    def exact_name(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError('Use a nonblank region name without surrounding whitespace')
        return value

    @field_validator('rate', 'free_from', mode='before')
    @classmethod
    def money(cls, value):
        if value is None:
            return value
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,8}(?:\.[0-9]{1,2})?', value):
            raise ValueError('Use a nonnegative decimal string with at most two decimal places')
        return format(Decimal(value), '.2f')

    @field_validator('countries')
    @classmethod
    def region(cls, values):
        if len(set(values)) != len(values) or any(value not in COUNTRIES for value in values):
            raise ValueError('Distinct ISO country codes required')
        return sorted(values)


class ShippingRules(Contract):
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    zones: list[ShippingZone] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def distinct_regions(self):
        keys, countries = set(), set()
        for zone in self.zones:
            if zone.key in keys or countries.intersection(zone.countries):
                raise ValueError('Shipping regions cannot overlap')
            keys.add(zone.key)
            countries.update(zone.countries)
        return self

    def quote(self, country: str, subtotal: Decimal) -> Decimal | None:
        if country not in COUNTRIES or not isinstance(subtotal, Decimal) or not subtotal.is_finite() or subtotal < 0:
            raise ValueError('Invalid quotation input')
        zone = next((zone for zone in self.zones if country in zone.countries), None)
        if zone is None:
            return None
        return Decimal('0.00') if zone.free_from is not None and subtotal >= Decimal(zone.free_from) else Decimal(zone.rate)
