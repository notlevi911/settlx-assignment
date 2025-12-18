"""
Social Sentiment endpoint - /v1/social/sentiment:score
Multi-source social signal analysis.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
from typing import List
import hashlib

from app.api.v1.schemas.requests import SocialSentimentRequest
from app.api.v1.schemas.responses import (
    SocialSentimentResponse,
    SentimentMetrics,
    AttentionMetrics,
    CoordinationMetrics,
    SourceBreakdown,
    TopPost,
    Evidence,
    StructuredError,
    ErrorCode
)
from app.services.cryptopanic_client import CryptoPanicClient

router = APIRouter()


@router.post("/social/sentiment:score", response_model=SocialSentimentResponse)
async def analyze_social_sentiment(request: SocialSentimentRequest):
    """
    **Social Sentiment Analysis**
    
    Analyzes social narrative and sentiment across multiple sources.
    
    Supported sources:
    - news: CryptoPanic aggregated crypto news
    
    Unsupported (will return structured error):
    - x (Twitter): Not yet implemented
    - reddit: Not yet implemented
    - youtube: Not yet implemented
    
    Returns sentiment, attention spikes, and coordination detection.
    """
    by_source: List[SourceBreakdown] = []
    all_errors: List[StructuredError] = []
    all_warnings: List[str] = []
    top_posts: List[TopPost] = []
    evidence_list: List[Evidence] = []
    
    # Calculate time window in hours
    lookback_hours = int((request.lookback.to - request.lookback.from_time).total_seconds() / 3600)
    
    # Analyze each requested source
    for source in request.sources:
        if source.lower() == "news":
            try:
                breakdown = await _analyze_news_source(
                    request.asset,
                    request.keywords,
                    lookback_hours,
                    request.limits.max_items_per_source,
                    request.options
                )
                by_source.append(breakdown)
                
                # Collect top posts
                if breakdown.errors:
                    all_errors.extend(breakdown.errors)
                
            except Exception as e:
                all_errors.append(StructuredError(
                    code=ErrorCode.UPSTREAM_ERROR,
                    message=f"News analysis failed: {str(e)}",
                    source="cryptopanic",
                    retryable=True
                ))
        
        elif source.lower() in ["x", "twitter", "reddit", "youtube"]:
            # Unsupported source - add structured error
            all_errors.append(StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=f"Source '{source}' not yet implemented",
                source=source,
                retryable=False
            ))
            
            by_source.append(SourceBreakdown(
                source=source,
                item_count=0,
                errors=[StructuredError(
                    code=ErrorCode.UNSUPPORTED_SOURCE,
                    message=f"Source '{source}' not yet implemented",
                    source=source,
                    retryable=False
                )]
            ))
        
        else:
            all_warnings.append(f"Unknown source '{source}' ignored")
    
    # Calculate aggregate metrics
    sentiment = _calculate_aggregate_sentiment(by_source)
    attention = _calculate_attention_metrics(by_source, lookback_hours)
    coordination = _detect_coordination(by_source)
    
    # Extract top posts
    top_posts = _extract_top_posts(by_source, request.options.return_top_posts)
    
    # Add evidence
    evidence_list.append(Evidence(
        provider="cryptopanic",
        timestamp=datetime.now(timezone.utc),
        ref="https://cryptopanic.com",
        note=f"Analyzed {sum(s.item_count for s in by_source)} news items"
    ))
    
    return SocialSentimentResponse(
        asset={"symbol": request.asset.symbol, "name": request.asset.name or ""},
        lookback={
            "from": request.lookback.from_time.isoformat(),
            "to": request.lookback.to.isoformat()
        },
        timestamp=datetime.now(timezone.utc),
        sentiment=sentiment,
        attention=attention,
        coordination=coordination,
        by_source=by_source,
        top_posts=top_posts,
        evidence=evidence_list,
        errors=all_errors,
        warnings=all_warnings
    )


async def _analyze_news_source(
    asset,
    keywords: List[str],
    lookback_hours: int,
    max_items: int,
    options
) -> SourceBreakdown:
    """Analyze news via CryptoPanic."""
    client = CryptoPanicClient()
    
    # Fetch news for primary keyword (asset symbol)
    news_data = await client.get_news(asset.symbol, hours=lookback_hours)
    
    if news_data.get("error"):
        return SourceBreakdown(
            source="news",
            item_count=0,
            errors=[StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=news_data["error"],
                source="cryptopanic",
                retryable=True
            )]
        )
    
    items = news_data["results"][:max_items]
    
    # Dedupe if requested
    if options.dedupe:
        items = _dedupe_articles(items)
    
    # Calculate sentiment
    sentiment_data = client.analyze_sentiment(items)
    avg_sentiment = sentiment_data.get("score")
    
    # Extract keywords
    top_keywords = _extract_keywords(items)
    
    return SourceBreakdown(
        source="news",
        item_count=len(items),
        sentiment_avg=avg_sentiment,
        top_keywords=top_keywords[:10],
        errors=[]
    )


def _dedupe_articles(items: List[dict]) -> List[dict]:
    """Remove duplicate articles based on title similarity."""
    seen_titles = set()
    deduped = []
    
    for item in items:
        title = item.get("title", "").lower().strip()
        # Simple deduplication - could use fuzzy matching
        if title and title not in seen_titles:
            seen_titles.add(title)
            deduped.append(item)
    
    return deduped


def _extract_keywords(items: List[dict]) -> List[str]:
    """Extract top keywords from article titles."""
    from collections import Counter
    import re
    
    # Common words to exclude
    stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", 
                 "of", "with", "by", "from", "up", "about", "into", "through", "during",
                 "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
                 "do", "does", "did", "will", "would", "could", "should", "may", "might"}
    
    words = []
    for item in items:
        title = item.get("title", "").lower()
        # Extract words (alphanumeric + hyphens)
        tokens = re.findall(r'\b[a-z0-9-]+\b', title)
        words.extend([w for w in tokens if len(w) > 3 and w not in stopwords])
    
    # Count frequencies
    counter = Counter(words)
    return [word for word, count in counter.most_common(20)]


def _calculate_aggregate_sentiment(by_source: List[SourceBreakdown]) -> SentimentMetrics:
    """Calculate overall sentiment from all sources."""
    sentiments = [s.sentiment_avg for s in by_source if s.sentiment_avg is not None]
    total_items = sum(s.item_count for s in by_source)
    
    if not sentiments or total_items == 0:
        return SentimentMetrics(
            score=None,
            confidence=0.0,
            distribution=None,
            sample_size=0
        )
    
    # Weighted average
    avg_sentiment = sum(sentiments) / len(sentiments)
    
    # Calculate confidence based on sample size and agreement
    import math
    sample_confidence = min(math.log(total_items + 1) / math.log(100), 1.0)
    
    # Agreement (standard deviation of sentiments)
    if len(sentiments) > 1:
        import statistics
        stdev = statistics.stdev(sentiments)
        agreement_confidence = 1.0 - min(stdev / 2, 1.0)
    else:
        agreement_confidence = 1.0
    
    confidence = (0.7 * sample_confidence + 0.3 * agreement_confidence)
    
    return SentimentMetrics(
        score=round(avg_sentiment, 3),
        confidence=round(confidence, 2),
        distribution=None,  # Would need to aggregate from individual sources
        sample_size=total_items
    )


def _calculate_attention_metrics(by_source: List[SourceBreakdown], lookback_hours: int) -> AttentionMetrics:
    """Calculate attention metrics and spike detection."""
    total_items = sum(s.item_count for s in by_source)
    
    # Calculate daily rate
    current_daily = (total_items / lookback_hours) * 24 if lookback_hours > 0 else 0
    
    # For spike detection, we'd need historical baseline
    # For now, use simple threshold
    baseline_daily = max(current_daily * 0.7, 5)  # Estimate baseline as 70% of current
    
    spike_detected = current_daily > baseline_daily * 2  # 2x baseline = spike
    percentile = min((current_daily / max(baseline_daily, 1)) * 50, 100)
    
    # Anomaly score (0-100)
    anomaly_score = min((current_daily / max(baseline_daily, 1) - 1) * 50, 100)
    
    return AttentionMetrics(
        baseline_daily_count=round(baseline_daily, 1),
        current_daily_count=round(current_daily, 1),
        spike_detected=spike_detected,
        percentile=round(percentile, 1),
        anomaly_score=round(max(anomaly_score, 0), 1)
    )


def _detect_coordination(by_source: List[SourceBreakdown]) -> CoordinationMetrics:
    """Detect coordinated narrative patterns."""
    # This would analyze source diversity, timing patterns, etc.
    # Placeholder implementation
    
    total_sources = sum(len(s.top_keywords) for s in by_source)
    unique_keywords = len(set(
        kw for s in by_source for kw in s.top_keywords
    ))
    
    diversity_score = unique_keywords / max(total_sources, 1) if total_sources > 0 else 0
    diversity_score = min(diversity_score, 1.0)
    
    suspected_coordination = diversity_score < 0.3  # Low diversity = possible coordination
    
    evidence = []
    if suspected_coordination:
        evidence.append(f"Low keyword diversity: {diversity_score:.2f}")
    
    return CoordinationMetrics(
        source_diversity_score=round(diversity_score, 2),
        unique_sources=unique_keywords,
        total_sources=total_sources,
        suspected_coordination=suspected_coordination,
        evidence=evidence
    )


def _extract_top_posts(by_source: List[SourceBreakdown], limit: int) -> List[TopPost]:
    """Extract top posts from sources."""
    # Would need to collect actual posts during analysis
    # Placeholder for now
    return []
