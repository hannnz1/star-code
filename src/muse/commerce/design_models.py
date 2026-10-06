"""Versioned, constrained storefront design; never executable code."""
from typing import Literal, Annotated
from pydantic import Field, model_validator, field_validator
from muse.commerce.models import Contract, SiteBlueprint


class SectionProps(Contract):
    title: str = Field(default='', max_length=160)
    text: str = Field(default='', max_length=4000)
    button_label: str = Field(default='', max_length=80)
    link: str = Field(default='/shop/', pattern=r'^/([a-z0-9-][a-z0-9/-]*)?$')
    media_id: str | None = Field(default=None, max_length=200)
    alt: str = Field(default='', max_length=200)
    items: list[Annotated[str, Field(max_length=500)]] = Field(default_factory=list, max_length=12)


class DesignSection(Contract):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    kind: Literal['hero', 'categories', 'products', 'story', 'faq']
    enabled: bool = True
    props: SectionProps


class HeroSection(DesignSection):
    kind: Literal['hero']


class CategoriesSection(DesignSection):
    kind: Literal['categories']


class ProductsSection(DesignSection):
    kind: Literal['products']


class StorySection(DesignSection):
    kind: Literal['story']


class FaqSection(DesignSection):
    kind: Literal['faq']


Section = Annotated[HeroSection | CategoriesSection | ProductsSection | StorySection | FaqSection, Field(discriminator='kind')]


class ThemeTokens(Contract):
    background: str = Field(default='#faf9f6', pattern=r'^#[a-fA-F0-9]{6}$')
    text: str = Field(default='#242424', pattern=r'^#[a-fA-F0-9]{6}$')
    accent: str = Field(default='#6554c0', pattern=r'^#[a-fA-F0-9]{6}$')
    font: Literal['sans', 'serif'] = 'sans'


class StoreDesignDocument(Contract):
    schema_version: Literal[1] = 1
    project_id: str
    project_revision: int = Field(ge=1)
    revision: int = Field(ge=1)
    blueprint_plan_id: str
    blueprint_revision: int = Field(ge=1)
    theme_tokens: ThemeTokens = Field(default_factory=ThemeTokens)
    home_sections: list[Section] = Field(max_length=20)

    @field_validator('home_sections', mode='before')
    @classmethod
    def normalize_sections(cls, value):
        if isinstance(value, list):
            return [section.model_dump(mode='json') if isinstance(section, DesignSection) else section for section in value]
        return value

    @model_validator(mode='after')
    def unique_ids(self):
        if len({s.id for s in self.home_sections}) != len(self.home_sections):
            raise ValueError('Duplicate section identity')
        return self


class DesignInitialize(Contract):
    expected_project_revision: int = Field(ge=1, strict=True)


class DesignSave(DesignInitialize):
    expected_revision: int = Field(ge=1, strict=True)
    client_request_id: str = Field(min_length=1, max_length=200)
    document: StoreDesignDocument
