from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_serializer,
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


_IPO_STOCK_CORE = frozenset(
    {
        "id",
        "companyName",
        "ticker",
        "market",
        "offerPrice",
        "subscriptionStart",
        "subscriptionEnd",
        "listingDate",
        "status",
        "memo",
    }
)


class IpoStockOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    company_name: str = Field(serialization_alias="companyName")
    ticker: str | None = None
    market: str | None = None
    offer_price: int | None = Field(serialization_alias="offerPrice")
    subscription_start: date | None = Field(serialization_alias="subscriptionStart")
    subscription_end: date | None = Field(serialization_alias="subscriptionEnd")
    listing_date: date | None = Field(serialization_alias="listingDate")
    status: IpoStockStatus
    memo: str | None = None
    status_raw: str | None = Field(default=None, serialization_alias="statusRaw")
    source_no: str | None = Field(default=None, serialization_alias="sourceNo")
    detail_url: str | None = Field(default=None, serialization_alias="detailUrl")
    underwriters: str | None = None
    hope_price: str | None = Field(default=None, serialization_alias="hopePrice")
    hope_price_low: int | float | None = Field(
        default=None, serialization_alias="hopePriceLow"
    )
    hope_price_high: int | float | None = Field(
        default=None, serialization_alias="hopePriceHigh"
    )
    final_price: str | None = Field(default=None, serialization_alias="finalPrice")
    offering_shares: str | None = Field(
        default=None, serialization_alias="offeringShares"
    )
    offering_shares_count: int | float | None = Field(
        default=None, serialization_alias="offeringSharesCount"
    )
    par_value: str | None = Field(default=None, serialization_alias="parValue")
    offering_amount: str | None = Field(
        default=None, serialization_alias="offeringAmount"
    )
    offering_mix: str | None = Field(default=None, serialization_alias="offeringMix")
    retail_comp_rate: str | None = Field(
        default=None, serialization_alias="retailCompRate"
    )
    inst_comp_rate: str | None = Field(default=None, serialization_alias="instCompRate")
    retail_apps: str | None = Field(default=None, serialization_alias="retailApps")
    bookbuilding_start: date | None = Field(
        default=None, serialization_alias="bookbuildingStart"
    )
    bookbuilding_end: date | None = Field(
        default=None, serialization_alias="bookbuildingEnd"
    )
    payment_date: date | None = Field(default=None, serialization_alias="paymentDate")
    refund_date: date | None = Field(default=None, serialization_alias="refundDate")
    allotment_date: date | None = Field(
        default=None, serialization_alias="allotmentDate"
    )
    ir_period: str | None = Field(default=None, serialization_alias="irPeriod")
    lockup_ratio: str | None = Field(default=None, serialization_alias="lockupRatio")
    industry: str | None = None
    ceo: str | None = None
    hq: str | None = None
    products: str | None = None
    company_type: str | None = Field(default=None, serialization_alias="companyType")
    homepage: str | None = None
    major_shareholder: str | None = Field(
        default=None, serialization_alias="majorShareholder"
    )
    revenue: str | None = None
    net_income: str | None = Field(default=None, serialization_alias="netIncome")
    capital: str | None = None
    open_price_krw: int | float | None = Field(
        default=None, serialization_alias="openPriceKrw"
    )
    open_vs_ipo_pct: int | float | None = Field(
        default=None, serialization_alias="openVsIpoPct"
    )
    first_close_krw: int | float | None = Field(
        default=None, serialization_alias="firstCloseKrw"
    )
    collected_at: datetime | None = Field(
        default=None, serialization_alias="collectedAt"
    )
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")

    @model_serializer(mode="wrap")
    def omit_empty_view_fields(self, serializer: Any) -> dict[str, Any]:
        data = serializer(self)
        return {
            key: value
            for key, value in data.items()
            if key in _IPO_STOCK_CORE or value is not None
        }


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


RelationKind = Literal["table", "view"]


class TableOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: RelationKind = "table"
    columns: list[ColumnOut]


class RoutineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    args: str
    result: str


class RoutineListOut(BaseModel):
    items: list[RoutineOut]


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
