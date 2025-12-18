"""
Social Sentiment endpoint - /v1/social/sentiment:score
Multi-source social signal analysis (strict spec compliance).
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import hashlib
import uuid

from app.api.v1.schemas.requests import SocialSentimentRequest
from app.api.v1.schemas.responses import (
    SocialSentimentResponse,
    SocialDataSection,
    SentimentMetrics,
    AttentionMetrics,
    InfluencerPressure,
    BySourceSentiment,
    SourceSentiment,
    MentionVelocity,
    CreatorConcentration,
    TopCreator,
    Anomaly,
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
    **Social Sentiment Analysis (Strict Spec)**
    
    Analyzes social narrative with deterministic sentiment + attention + anomaly signals.
    
    Supported sources:
    - news: CryptoPanic aggregated crypto news
    
    Unsupported (structured errors):
    - x, reddit, youtube
    
    Returns strict spec response with request_id, as_of, and data wrapper.
    """
    all_errors: List[StructuredError] = []
    all_warnings: List[str] = []
    evidence_list: List[Evidence] = []
    
    # Calculate time window
    lookback_from = request.lookback.from_time
    lookback_to = request.lookback.to
    lookback_minutes = (lookback_to - lookback_from).total_seconds() / 60
    
    # Fetch news from CryptoPanic
    news_items = []
    news_status = "unsupported"
    news_sentiment_score = None
    news_volume = 0
    news_engagement = 0
    
    if "news" in request.sources:
        try:
            client = CryptoPanicClient()
            lookback_hours = int((lookback_to - lookback_from).total_seconds() / 3600)
            news_data = await client.get_news(
                request.asset.symbol,
                hours=lookback_hours
            )
            
            if news_data.get("error"):
                all_errors.append(StructuredError(
                    code=ErrorCode.UPSTREAM_ERROR,
                    message=news_data["error"],
                    source="cryptopanic",
                    retryable=True
                ))
                news_status = "partial"
            else:
                news_items = news_data["results"][:request.limits.max_items_per_source]
                news_status = "ok"
                
                # Dedupe if requested
                if request.options.dedupe:
                    news_items = _dedupe_by_text_hash(news_items)
                
                news_volume = len(news_items)
                news_sentiment_score = _calculate_deterministic_sentiment(news_items)
                
                evidence_list.append(Evidence(
                    provider="cryptopanic",
                    timestamp=datetime.now(timezone.utc),
                    ref="https://cryptopanic.com",
                    note=f"Analyzed {news_volume} news items"
                ))
                
        except Exception as e:
            all_errors.append(StructuredError(
                code=ErrorCode.UPSTREAM_ERROR,
                message=f"CryptoPanic error: {str(e)}",
                source="cryptopanic",
                retryable=True
            ))
            news_status = "partial"
    
    # Build by_source sentiment
    by_source_sentiment = BySourceSentiment()
    
    if "news" in request.sources:
        by_source_sentiment.news = SourceSentiment(
            score=news_sentiment_score,
            volume=news_volume,
            engagement=news_engagement,
            status=news_status
        )
    
    # Handle unsupported sources
    for source in request.sources:
        source_lower = source.lower()
        if source_lower in ["x", "twitter"]:
            by_source_sentiment.x = SourceSentiment(
                score=None,
                volume=0,
                engagement=0,
                status="unsupported"
            )
            all_errors.append(StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=f"Source '{source}' not yet implemented",
                source=source,
                retryable=False
            ))
        elif source_lower == "reddit":
            by_source_sentiment.reddit = SourceSentiment(
                score=None,
                volume=0,
                engagement=0,
                status="unsupported"
            )
            all_errors.append(StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=f"Source 'reddit' not yet implemented",
                source=source,
                retryable=False
            ))
        elif source_lower == "youtube":
            by_source_sentiment.youtube = SourceSentiment(
                score=None,
                volume=0,
                engagement=0,
                status="unsupported"
            )
            all_errors.append(StructuredError(
                code=ErrorCode.UNSUPPORTED_SOURCE,
                message=f"Source 'youtube' not yet implemented",
                source=source,
                retryable=False
            ))
    
    # Calculate overall sentiment
    sentiment_label = _classify_sentiment_label(news_sentiment_score)
    sentiment_confidence = _calculate_confidence(news_volume, news_items)
    
    sentiment = SentimentMetrics(
        score=news_sentiment_score,
        label=sentiment_label,
        confidence=sentiment_confidence,
        by_source=by_source_sentiment
    )
    
    # Calculate attention metrics
    mention_velocity = MentionVelocity(
        per_min=news_volume / lookback_minutes if lookback_minutes > 0 else 0.0,
        zscore_vs_30d=_calculate_zscore_vs_baseline(news_volume)
    )
    
    unique_authors = _count_unique_authors(news_items)
    creator_concentration = CreatorConcentration(
        top_10_share=_calculate_top_10_share(news_items)
    )
    
    attention = AttentionMetrics(
        mention_velocity=mention_velocity,
        unique_authors=unique_authors,
        creator_concentration=creator_concentration
    )
    
    # Calculate influencer pressure
    top_creators = _extract_top_creators(news_items, limit=5)
    influencer_score = _calculate_influencer_score(top_creators, news_volume)
    
    influencer_pressure = InfluencerPressure(
        score=influencer_score,
        top_creators=top_creators
    )
    
    # Detect anomalies
    anomalies = _detect_anomalies(
        mention_velocity.zscore_vs_30d,
        creator_concentration.top_10_share,
        unique_authors
    )
    
    # Extract top posts
    top_posts_list = _extract_top_posts(
        news_items,
        limit=request.options.return_top_posts
    )
    
    # Build data section
    data = SocialDataSection(
        sentiment=sentiment,
        attention=attention,
        influencer_pressure=influencer_pressure,
        anomalies=anomalies,
        top_posts=top_posts_list
    )
    
    # Build response
    return SocialSentimentResponse(
        request_id=str(uuid.uuid4()),
        as_of=datetime.now(timezone.utc).isoformat(),
        data=data,
        evidence=evidence_list,
        warnings=all_warnings,
        errors=all_errors
    )


# ===== Helper Functions =====

def _dedupe_by_text_hash(items: List[dict]) -> List[dict]:
    """
    Deduplicate items by normalized text hash.
    Keeps item with max engagement per hash.
    """
    from collections import defaultdict
    
    hash_to_items = defaultdict(list)
    
    for item in items:
        text = item.get("title", "") + " " + item.get("url", "")
        # Normalize
        normalized = text.lower().strip()
        text_hash = hashlib.sha256(normalized.encode()).hexdigest()
        hash_to_items[text_hash].append(item)
    
    deduped = []
    for items_group in hash_to_items.values():
        # Keep item with max votes
        best_item = max(items_group, key=lambda x: x.get("votes", {}).get("positive", 0))
        deduped.append(best_item)
    
    return deduped


def _calculate_deterministic_sentiment(items: List[dict]) -> Optional[float]:
    """
    Calculate deterministic sentiment from CryptoPanic votes.
    Returns -1 to +1, or None if no items.
    """
    if not items:
        return None
    
    total_score = 0.0
    count = 0
    
    for item in items:
        votes = item.get("votes", {})
        positive = votes.get("positive", 0)
        negative = votes.get("negative", 0)
        important = votes.get("important", 0)
        
        # Simple heuristic: positive/important boost, negative reduce
        if positive + negative + important > 0:
            item_score = (positive + important * 0.5 - negative) / (positive + negative + important)
            total_score += item_score
            count += 1
    
    if count == 0:
        return 0.0  # Neutral if no vote data
    
    return total_score / count


def _classify_sentiment_label(score: Optional[float]) -> Optional[str]:
    """Classify sentiment score into label."""
    if score is None:
        return None
    
    if score <= -0.6:
        return "very_negative"
    elif score <= -0.2:
        return "negative"
    elif score <= -0.05:
        return "slightly_negative"
    elif score <= 0.05:
        return "neutral"
    elif score <= 0.2:
        return "slightly_positive"
    elif score <= 0.6:
        return "positive"
    else:
        return "very_positive"


def _calculate_confidence(volume: int, items: List[dict]) -> float:
    """
    Calculate confidence based on sample size and data quality.
    Returns 0-1.
    """
    if volume == 0:
        return 0.0
    
    # Base confidence from volume
    volume_confidence = min(volume / 50.0, 1.0)  # 50+ items = max confidence
    
    # Agreement factor: check vote consistency
    if items:
        vote_counts = [item.get("votes", {}).get("positive", 0) + 
                      item.get("votes", {}).get("negative", 0) 
                      for item in items]
        items_with_votes = sum(1 for vc in vote_counts if vc > 0)
        vote_confidence = items_with_votes / len(items) if items else 0.5
    else:
        vote_confidence = 0.5
    
    # Combine
    return (volume_confidence * 0.7 + vote_confidence * 0.3)


def _calculate_zscore_vs_baseline(current_count: int) -> float:
    """
    Calculate z-score vs 30-day baseline.
    Simplified: assumes baseline mean=10, std=5.
    Real implementation would maintain rolling stats.
    """
    baseline_mean = 10.0
    baseline_std = 5.0
    
    if baseline_std == 0:
        return 0.0
    
    zscore = (current_count - baseline_mean) / baseline_std
    return zscore


def _count_unique_authors(items: List[dict]) -> Optional[int]:
    """Count unique authors from news items."""
    if not items:
        return None
    
    authors = set()
    for item in items:
        source_info = item.get("source", {})
        if isinstance(source_info, dict):
            author = source_info.get("title") or source_info.get("domain")
            if author:
                authors.add(author)
    
    return len(authors) if authors else None


def _calculate_top_10_share(items: List[dict]) -> float:
    """
    Calculate what % of content comes from top 10 creators.
    """
    if not items:
        return 0.0
    
    from collections import Counter
    
    # Count items per author/source
    author_counts = Counter()
    for item in items:
        source_info = item.get("source", {})
        if isinstance(source_info, dict):
            author = source_info.get("title") or source_info.get("domain", "unknown")
            author_counts[author] += 1
    
    if not author_counts:
        return 0.0
    
    # Top 10 share
    top_10 = author_counts.most_common(10)
    top_10_count = sum(count for _, count in top_10)
    
    return top_10_count / len(items)


def _extract_top_creators(items: List[dict], limit: int = 5) -> List[TopCreator]:
    """Extract top creators/sources by engagement."""
    from collections import defaultdict
    
    creator_data = defaultdict(lambda: {"engagement": 0, "sentiment": [], "posts": []})
    
    for item in items:
        source_info = item.get("source", {})
        if isinstance(source_info, dict):
            handle = source_info.get("title") or source_info.get("domain", "unknown")
            
            votes = item.get("votes", {})
            engagement = sum(votes.values())
            
            creator_data[handle]["engagement"] += engagement
            creator_data[handle]["posts"].append(str(item.get("id", "unknown")))
            
            # Sentiment for this item
            positive = votes.get("positive", 0)
            negative = votes.get("negative", 0)
            if positive + negative > 0:
                item_sent = (positive - negative) / (positive + negative)
                creator_data[handle]["sentiment"].append(item_sent)
    
    # Convert to TopCreator objects
    top_creators = []
    for handle, data in sorted(creator_data.items(), key=lambda x: x[1]["engagement"], reverse=True)[:limit]:
        avg_sentiment = sum(data["sentiment"]) / len(data["sentiment"]) if data["sentiment"] else 0.0
        top_creators.append(TopCreator(
            handle=handle,
            followers=0,  # Not available from CryptoPanic
            engagement=data["engagement"],
            sentiment=avg_sentiment,
            post_id=str(data["posts"][0]) if data["posts"] else "unknown",
            source="news"
        ))
    
    return top_creators


def _calculate_influencer_score(creators: List[TopCreator], total_volume: int) -> float:
    """
    Calculate influencer pressure score (0-1).
    Based on concentration and engagement.
    """
    if not creators or total_volume == 0:
        return 0.0
    
    total_engagement = sum(c.engagement for c in creators)
    top_3_engagement = sum(c.engagement for c in creators[:3])
    
    # High score if top creators have high engagement relative to total
    concentration = top_3_engagement / total_engagement if total_engagement > 0 else 0.0
    
    # Scale by total volume (more items = more pressure)
    volume_factor = min(total_volume / 50.0, 1.0)
    
    return concentration * volume_factor


def _detect_anomalies(
    zscore: float,
    concentration: float,
    unique_authors: Optional[int]
) -> List[Anomaly]:
    """Detect anomalies: volume spikes and coordination signals."""
    anomalies = []
    
    # Volume spike detection
    if zscore > 3.0:
        anomalies.append(Anomaly(
            type="volume_spike",
            severity="high",
            reason=f"Mention velocity {zscore:.1f}σ above 30-day baseline"
        ))
    elif zscore > 2.0:
        anomalies.append(Anomaly(
            type="volume_spike",
            severity="medium",
            reason=f"Mention velocity {zscore:.1f}σ above 30-day baseline"
        ))
    elif zscore > 1.5:
        anomalies.append(Anomaly(
            type="volume_spike",
            severity="low",
            reason=f"Mention velocity {zscore:.1f}σ above baseline"
        ))
    
    # Coordination signal detection
    if concentration > 0.8:
        anomalies.append(Anomaly(
            type="coordination_signal",
            severity="high",
            reason=f"Top 10 creators account for {concentration*100:.0f}% of content"
        ))
    elif concentration > 0.6 and unique_authors is not None and unique_authors < 5:
        anomalies.append(Anomaly(
            type="coordination_signal",
            severity="medium",
            reason=f"High concentration ({concentration*100:.0f}%) with only {unique_authors} unique authors"
        ))
    
    return anomalies


def _extract_top_posts(items: List[dict], limit: int = 20) -> List[TopPost]:
    """Extract top posts by engagement with text hashes."""
    # Sort by engagement (total votes)
    sorted_items = sorted(
        items,
        key=lambda x: sum(x.get("votes", {}).values()),
        reverse=True
    )[:limit]
    
    top_posts = []
    for item in sorted_items:
        # Create text hash
        text = item.get("title", "") + " " + item.get("url", "")
        normalized = text.lower().strip()
        text_hash = "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()[:16]
        
        # Calculate sentiment
        votes = item.get("votes", {})
        positive = votes.get("positive", 0)
        negative = votes.get("negative", 0)
        if positive + negative > 0:
            sentiment = (positive - negative) / (positive + negative)
        else:
            sentiment = 0.0
        
        # Extract author
        source_info = item.get("source", {})
        author = None
        if isinstance(source_info, dict):
            author = source_info.get("title") or source_info.get("domain")
        
        top_posts.append(TopPost(
            source="news",
            id=str(item.get("id", "unknown")),
            url=item.get("url", ""),
            author=author,
            ts=item.get("published_at", datetime.now(timezone.utc).isoformat()),
            engagement=sum(votes.values()),
            sentiment=sentiment,
            text_hash=text_hash
        ))
    
    return top_posts
