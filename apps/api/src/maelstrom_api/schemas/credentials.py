from pydantic import BaseModel, Field


class HyperliquidCredsIn(BaseModel):
    """Body for POST /accounts/{id}/credentials when kind starts with live_hl_."""

    wallet_address: str = Field(min_length=4, max_length=120)
    private_key: str = Field(min_length=10, max_length=256)


class CredentialState(BaseModel):
    has_credentials: bool
    wallet_address: str | None = None
