from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)


class AuthMeOut(BaseModel):
    id: str
    email: str | None


IpoStockStatus = Literal[
    "scheduled",
    "subscription_open",
    "subscription_closed",
    "listed",
    "cancelled",
]

CompanyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
Ticker = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=32, to_upper=True
    ),
]
Market = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]
Memo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
OfferPrice = Annotated[StrictInt, Field(ge=1)]


class _IpoStockInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_by_alias=True,
        validate_by_name=False,
    )

    @field_validator("ticker", "market", "memo", mode="before", check_fields=False)
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @staticmethod
    def _validate_subscription_range(start: date | None, end: date | None) -> None:
        if start is not None and end is not None and end < start:
            raise ValueError("subscriptionEnd must not be before subscriptionStart")


class IpoStockCreate(_IpoStockInput):
    company_name: CompanyName = Field(alias="companyName")
    ticker: Ticker | None = None
    market: Market | None = None
    offer_price: OfferPrice | None = Field(default=None, alias="offerPrice")
    subscription_start: date | None = Field(default=None, alias="subscriptionStart")
    subscription_end: date | None = Field(default=None, alias="subscriptionEnd")
    listing_date: date | None = Field(default=None, alias="listingDate")
    status: IpoStockStatus = "scheduled"
    memo: Memo | None = None

    @model_validator(mode="after")
    def validate_subscription_range(self) -> "IpoStockCreate":
        self._validate_subscription_range(
            self.subscription_start, self.subscription_end
        )
        return self


class IpoStockUpdate(_IpoStockInput):
    company_name: CompanyName | None = Field(default=None, alias="companyName")
    ticker: Ticker | None = None
    market: Market | None = None
    offer_price: OfferPrice | None = Field(default=None, alias="offerPrice")
    subscription_start: date | None = Field(default=None, alias="subscriptionStart")
    subscription_end: date | None = Field(default=None, alias="subscriptionEnd")
    listing_date: date | None = Field(default=None, alias="listingDate")
    status: IpoStockStatus | None = None
    memo: Memo | None = None

    @field_validator("company_name", "status", mode="before")
    @classmethod
    def reject_null_for_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("This field must not be null")
        return value

    @model_validator(mode="after")
    def require_changes_and_validate_subscription_range(self) -> "IpoStockUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        self._validate_subscription_range(
            self.subscription_start, self.subscription_end
        )
        return self


class IpoStockOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    company_name: str = Field(serialization_alias="companyName")
    ticker: str | None = None
    market: str | None = None
    offer_price: int | None = Field(serialization_alias="offerPrice")
    subscription_start: date | None = Field(serialization_alias="subscriptionStart")
    subscription_end: date | None = Field(serialization_alias="subscriptionEnd")
    listing_date: date | None = Field(serialization_alias="listingDate")
    status: IpoStockStatus
    memo: str | None = None


class IpoStockListOut(BaseModel):
    items: list[IpoStockOut]
    count: int = Field(ge=0)


ColumnType = Literal[
    "text",
    "integer",
    "bigint",
    "boolean",
    "date",
    "timestamptz",
    "numeric",
    "uuid",
    "jsonb",
]
IDENT_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
ColumnName = Annotated[str, StringConstraints(pattern=IDENT_PATTERN)]


class ColumnOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    nullable: bool
    primary_key: bool = Field(serialization_alias="primaryKey")


class TableOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[ColumnOut]


class TableListOut(BaseModel):
    items: list[TableOut]


class ColumnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ColumnName
    type: ColumnType
    nullable: bool = True


class ColumnNameOut(BaseModel):
    name: str


class RowListOut(BaseModel):
    items: list[dict[str, Any]]
    count: int = Field(ge=0)
