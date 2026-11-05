from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    financial_data_provider: str = Field(
        default="yfinance", alias="FINANCIAL_DATA_PROVIDER"
    )
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
    fmp_api_key: str = Field(default="", alias="FMP_API_KEY")
    fmp_base_url: str = Field(
        default="https://financialmodelingprep.com/stable", alias="FMP_BASE_URL"
    )
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    strands_provider: str = Field(default="bedrock", alias="STRANDS_PROVIDER")
    strands_model: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        alias="STRANDS_MODEL",
    )
    ollama_host: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_HOST")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        alias="GROQ_BASE_URL",
    )
    cache_default_ttl: int = Field(default=3600, alias="CACHE_DEFAULT_TTL")
    cache_max_size: int = Field(default=512, alias="CACHE_MAX_SIZE")

    @property
    def financial_source(self) -> str:
        return self.financial_data_provider.strip().lower()

    def api_key_status(self) -> dict[str, bool]:
        """Readiness of each credential the active configuration depends on."""
        status: dict[str, bool] = {}
        source = self.financial_source
        if source == "alphavantage":
            status["Alpha Vantage (market data)"] = bool(self.alpha_vantage_api_key)
        elif source == "fmp":
            status["Financial Modeling Prep (market data)"] = bool(self.fmp_api_key)
        else:
            status["Yahoo Finance (market data)"] = True
        status["Tavily"] = bool(self.tavily_api_key)
        status["Strands model"] = bool(self.strands_model)
        if self.strands_provider.strip().lower() == "groq":
            status["Groq"] = bool(self.groq_api_key)
        return status


@lru_cache
def get_settings() -> Settings:
    return Settings()
