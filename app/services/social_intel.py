"""
Social Intel Service - Narrative and sentiment analysis.
Uses CryptoPanic API for news-based signals.
"""
from datetime import datetime
from typing import List
from app.core.models import SocialIntelResponse, CertainData, RiskFlagDetail
from app.core.enums import DataCertainty, RiskFlag
from app.services.cryptopanic_client import CryptoPanicClient


class SocialIntelService:
    """
    Analyzes social narrative and risk tone for tokens.
    Primarily INFERRED data with explicit UNKNOWNs where data is missing.
    """
    
    def __init__(self):
        self.client = CryptoPanicClient()
    
    async def analyze_social_intel(self, symbol: str) -> SocialIntelResponse:
        """
        Full social intelligence analysis.
        Classifies all data as PROVEN, INFERRED, or UNKNOWN.
        """
        risk_flags = []
        
        # Step 1: Fetch 24h news
        news_24h = await self.client.get_news(symbol, hours=24)
        
        if news_24h.get("error"):
            # Cannot fetch data - everything is UNKNOWN
            return self._build_unknown_response(symbol, news_24h["error"])
        
        news_count_24h = CertainData(
            value=news_24h["count"],
            certainty=DataCertainty.PROVEN,
            source="CryptoPanic API",
            reason=None
        )
        
        # Step 2: Fetch 7d news
        news_7d = await self.client.get_news(symbol, hours=168)  # 7 days = 168 hours
        
        news_count_7d = CertainData(
            value=news_7d["count"] if not news_7d.get("error") else None,
            certainty=DataCertainty.PROVEN if not news_7d.get("error") else DataCertainty.UNKNOWN,
            source="CryptoPanic API" if not news_7d.get("error") else None,
            reason=news_7d.get("error")
        )
        
        # Risk flag: Low attention
        if news_count_24h.value < 3:
            risk_flags.append(RiskFlagDetail(
                flag=RiskFlag.LOW_ATTENTION,
                evidence=f"Only {news_count_24h.value} news articles in past 24h",
                severity=4,
                certainty=DataCertainty.PROVEN
            ))
        
        # Step 3: Sentiment analysis (INFERRED)
        sentiment_data = self.client.analyze_sentiment(news_24h["results"])
        
        if sentiment_data["score"] is not None:
            sentiment_score = CertainData(
                value=sentiment_data["score"],
                certainty=DataCertainty.INFERRED,
                source="CryptoPanic vote aggregation",
                reason=f"Inferred from user votes on {news_count_24h.value} articles (confidence: {sentiment_data['confidence']})"
            )
            
            sentiment_distribution = CertainData(
                value=sentiment_data["distribution"],
                certainty=DataCertainty.INFERRED,
                source="CryptoPanic vote aggregation",
                reason=None
            )
            
            # Risk flag: Negative sentiment
            if sentiment_data["score"] < -0.3:
                risk_flags.append(RiskFlagDetail(
                    flag=RiskFlag.NEGATIVE_SENTIMENT,
                    evidence=f"Sentiment score: {sentiment_data['score']:.2f} (negative dominant)",
                    severity=6,
                    certainty=DataCertainty.INFERRED
                ))
        else:
            sentiment_score = CertainData(
                value=None,
                certainty=DataCertainty.UNKNOWN,
                source=None,
                reason="No news articles with sentiment votes available"
            )
            
            sentiment_distribution = CertainData(
                value=None,
                certainty=DataCertainty.UNKNOWN,
                source=None,
                reason="No news articles available"
            )
        
        # Step 4: Attention spike detection (INFERRED)
        if news_count_7d.value is not None and news_count_7d.value > 0:
            baseline_daily = news_count_7d.value / 7
            spike_data = self.client.detect_attention_spike(
                current_count=news_count_24h.value,
                baseline_count=int(baseline_daily)
            )
            
            attention_spike_detected = CertainData(
                value=spike_data["spike_detected"],
                certainty=DataCertainty.INFERRED,
                source="24h vs 7d baseline comparison",
                reason=spike_data["evidence"]
            )
            
            attention_percentile = CertainData(
                value=spike_data["percentile"],
                certainty=DataCertainty.INFERRED,
                source="Heuristic ratio calculation",
                reason=None
            )
        else:
            attention_spike_detected = CertainData(
                value=False,
                certainty=DataCertainty.UNKNOWN,
                source=None,
                reason="Insufficient historical data for baseline"
            )
            
            attention_percentile = CertainData(
                value=None,
                certainty=DataCertainty.UNKNOWN,
                source=None,
                reason="Insufficient historical data"
            )
        
        # Step 5: Source diversity (coordination detection) - INFERRED
        diversity_data = self.client.analyze_source_diversity(news_24h["results"])
        
        if diversity_data["diversity_score"] is not None:
            source_diversity = CertainData(
                value=diversity_data["diversity_score"],
                certainty=DataCertainty.INFERRED,
                source="News source domain analysis",
                reason=f"{diversity_data['unique_sources']} unique sources across {diversity_data['total_articles']} articles"
            )
            
            # Risk flag: Coordinated narrative (low diversity)
            if diversity_data["diversity_score"] < 0.5:
                risk_flags.append(RiskFlagDetail(
                    flag=RiskFlag.COORDINATED_NARRATIVE,
                    evidence=f"Low source diversity: {diversity_data['diversity_score']:.2f} ({diversity_data['unique_sources']} sources for {diversity_data['total_articles']} articles)",
                    severity=5,
                    certainty=DataCertainty.INFERRED
                ))
        else:
            source_diversity = CertainData(
                value=None,
                certainty=DataCertainty.UNKNOWN,
                source=None,
                reason="No news articles to analyze"
            )
        
        # Step 6: Narrative keywords (INFERRED)
        keywords = self.client.extract_narrative_keywords(news_24h["results"])
        
        narrative_keywords = CertainData(
            value=keywords,
            certainty=DataCertainty.INFERRED if keywords else DataCertainty.UNKNOWN,
            source="Frequency analysis of news titles",
            reason="Extracted from article titles" if keywords else "No articles available"
        )
        
        # Step 7: Calculate narrative risk score
        narrative_risk_score = self._calculate_narrative_risk(risk_flags, sentiment_data)
        
        return SocialIntelResponse(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            news_count_24h=news_count_24h,
            news_count_7d=news_count_7d,
            sentiment_score=sentiment_score,
            sentiment_distribution=sentiment_distribution,
            attention_spike_detected=attention_spike_detected,
            attention_percentile=attention_percentile,
            source_diversity=source_diversity,
            narrative_keywords=narrative_keywords,
            risk_flags=risk_flags,
            narrative_risk_score=narrative_risk_score
        )
    
    def _build_unknown_response(self, symbol: str, error: str) -> SocialIntelResponse:
        """Build response when API data is unavailable."""
        unknown_reason = f"CryptoPanic API error: {error}"
        
        return SocialIntelResponse(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            news_count_24h=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            news_count_7d=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            sentiment_score=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            sentiment_distribution=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            attention_spike_detected=CertainData(value=False, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            attention_percentile=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            source_diversity=CertainData(value=None, certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            narrative_keywords=CertainData(value=[], certainty=DataCertainty.UNKNOWN, source=None, reason=unknown_reason),
            risk_flags=[
                RiskFlagDetail(
                    flag=RiskFlag.NO_SOCIAL_DATA,
                    evidence=error,
                    severity=3,
                    certainty=DataCertainty.PROVEN
                )
            ],
            narrative_risk_score=50  # Unknown = medium risk
        )
    
    def _calculate_narrative_risk(self, risk_flags: List[RiskFlagDetail], sentiment_data: dict) -> int:
        """
        Calculate 0-100 narrative risk score.
        0 = positive/safe, 100 = critical negative sentiment.
        """
        base_score = sum(flag.severity for flag in risk_flags) * 2
        
        # Adjust for sentiment
        if sentiment_data.get("score") is not None:
            sentiment_score = sentiment_data["score"]
            if sentiment_score < -0.5:
                base_score += 20
            elif sentiment_score < 0:
                base_score += 10
            elif sentiment_score > 0.5:
                base_score -= 10
        
        return min(100, max(0, base_score))
