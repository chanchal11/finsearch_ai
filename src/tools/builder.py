from __future__ import annotations

from dataclasses import dataclass

from strands import tool

from src.core.cache import ICacheProvider, tool_kv_cache
from src.core.interfaces import IFinancialDataProvider, INewsDataProvider
from src.tools import fundamentals, market, news, valuation


@dataclass
class ToolBundle:
    fundamental_tools: list
    valuation_tools: list
    news_tools: list
    risk_tools: list
    market_tools: list

    @property
    def all_tools(self) -> list:
        seen: set[int] = set()
        merged: list = []
        for group in (
            self.fundamental_tools,
            self.valuation_tools,
            self.news_tools,
            self.market_tools,
            self.risk_tools,
        ):
            for item in group:
                if id(item) not in seen:
                    seen.add(id(item))
                    merged.append(item)
        return merged


def build_tool_bundle(
    financial: IFinancialDataProvider,
    news_provider: INewsDataProvider,
    cache: ICacheProvider,
    *,
    cache_ttl: int,
) -> ToolBundle:
    memo = lambda prefix: tool_kv_cache(cache, prefix=prefix, ttl=cache_ttl)  # noqa: E731

    @tool
    @memo("income")
    def get_income_statement(symbol: str, period: str = "annual") -> str:
        """Return the income statement for a ticker as Markdown."""
        return fundamentals.fetch_income_statement(financial, symbol, period)

    @tool
    @memo("balance")
    def get_balance_sheet(symbol: str, period: str = "annual") -> str:
        """Return the balance sheet for a ticker as Markdown."""
        return fundamentals.fetch_balance_sheet(financial, symbol, period)

    @tool
    @memo("cashflow")
    def get_cash_flow_statement(symbol: str, period: str = "annual") -> str:
        """Return the cash flow statement for a ticker as Markdown."""
        return fundamentals.fetch_cash_flow(financial, symbol, period)

    @tool
    @memo("ratios")
    def compute_key_ratios(symbol: str, period: str = "annual") -> str:
        """Compute liquidity, leverage, profitability, and FCF ratios."""
        return fundamentals.compute_key_ratios(financial, symbol, period)

    @tool
    @memo("trends")
    def get_financial_trends(symbol: str, years: int = 5) -> str:
        """Multi-year revenue growth, margins, and net income vs free cash flow (earnings quality)."""
        return fundamentals.fetch_financial_trends(financial, symbol, years)

    @tool
    @memo("dcf_scenarios")
    def run_dcf_scenarios(symbol: str, forecast_years: int = 5) -> str:
        """Run bear, base, and bull DCFs and compare each intrinsic value with the market price."""
        return valuation.run_dcf_scenarios(financial, symbol, forecast_years)

    @tool
    @memo("price_performance")
    def get_price_performance(symbol: str, peers: str = "", weeks: int = 104) -> str:
        """Compare return, volatility, max drawdown, and distance from the 52-week high for a ticker and peers."""
        return market.get_price_performance(financial, symbol, peers, weeks)

    @tool
    @memo("dcf")
    def run_dcf_model(
        symbol: str,
        growth_rate: float = 0.08,
        discount_rate: float = 0.1,
        terminal_growth_rate: float = 0.025,
        forecast_years: int = 5,
    ) -> str:
        """Run a Gordon Growth DCF with margin-of-safety vs market price."""
        return valuation.run_dcf_model(
            financial,
            symbol,
            growth_rate=growth_rate,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
            forecast_years=forecast_years,
        )

    @tool
    @memo("peers")
    def get_peer_multiples(peers: str, target: str = "") -> str:
        """Compare valuation multiples across comma-separated peer tickers.

        Pass the company under review as ``target`` to include it in the table next to the peer median.
        """
        return valuation.get_peer_multiples(financial, peers, target)

    @tool
    @memo("news_search")
    def search_recent_news(query: str, days: int = 7, max_results: int = 8) -> str:
        """Search recent financial news headlines."""
        return news.search_recent_news(news_provider, query, days, max_results)

    @tool
    @memo("news_desk")
    def news_desk(topic: str) -> str:
        """Produce a news desk brief for a company or theme."""
        return news.news_desk(news_provider, topic)

    @tool
    def analyze_sentiment(text: str) -> str:
        """Score headline/body text as Bullish, Bearish, or Neutral."""
        return news.analyze_sentiment(text)

    fundamental_tools = [
        get_income_statement,
        get_balance_sheet,
        get_cash_flow_statement,
        compute_key_ratios,
        get_financial_trends,
    ]
    valuation_tools = [run_dcf_model, run_dcf_scenarios, get_peer_multiples]
    news_tools = [search_recent_news, news_desk, analyze_sentiment]
    market_tools = [get_price_performance]
    risk_tools = fundamental_tools + news_tools + market_tools

    return ToolBundle(
        fundamental_tools=fundamental_tools,
        valuation_tools=valuation_tools,
        news_tools=news_tools,
        risk_tools=risk_tools,
        market_tools=market_tools,
    )
