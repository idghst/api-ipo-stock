from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer


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


class IpoStockSummaryOut(BaseModel):
    total: int = Field(ge=0)
    scheduled: int = Field(ge=0)
    subscription_open: int = Field(ge=0, serialization_alias="subscriptionOpen")
    subscription_closed: int = Field(ge=0, serialization_alias="subscriptionClosed")
    listed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    upcoming_subscription: int = Field(ge=0, serialization_alias="upcomingSubscription")
    upcoming_listing: int = Field(ge=0, serialization_alias="upcomingListing")


class IpoStockListOut(BaseModel):
    items: list[IpoStockOut]
    count: int = Field(ge=0)
    summary: IpoStockSummaryOut
    upcoming: list[IpoStockOut] = Field(default_factory=list)
