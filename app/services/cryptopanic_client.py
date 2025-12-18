"""
CryptoPanic API client.
Fetches crypto news and sentiment data.
"""
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.core.config import settings


class CryptoPanicClient:
    """Client for CryptoPanic news and sentiment API."""
    
    def __init__(self):
        self.base_url = settings.cryptopanic_base_url
        self.api_key = settings.cryptopanic_api_key
    
    async def get_news(
        self,
        symbol: str,
        hours: int = 24,
        kind: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch news for a token symbol.
        
        Args:
            symbol: Token ticker symbol (e.g., "BTC", "ETH")
            hours: Look back this many hours
            kind: Filter by news kind ("news" or "media")
        
        Returns:
            {results: [...], count: N, error: None}
        """
        if not self.api_key:
            return {
                "results": [],
                "count": 0,
                "error": "CryptoPanic API key not configured"
            }
        
        params = {
            "auth_token": self.api_key,
            "currencies": symbol.upper(),
            "public": "true",
        }
        
        if kind:
            params["kind"] = kind
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Use v2 API endpoint
                response = await client.get(f"{self.base_url}/posts/", params=params)
                response.raise_for_status()
                data = response.json()
                
                # Filter by time window (make cutoff timezone-aware)
                from datetime import timezone
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                results = data.get("results", [])
                
                filtered_results = []
                for item in results:
                    published_at_str = item.get("published_at", "")
                    if not published_at_str:
                        continue
                    
                    # Parse timezone-aware datetime
                    published_at = datetime.fromisoformat(
                        published_at_str.replace("Z", "+00:00")
                    )
                    if published_at >= cutoff:
                        filtered_results.append(item)
                
                return {
                    "results": filtered_results,
                    "count": len(filtered_results),
                    "error": None
                }
        
        except httpx.HTTPError as e:
            return {
                "results": [],
                "count": 0,
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "results": [],
                "count": 0,
                "error": f"Error fetching news: {str(e)}"
            }
    
    def analyze_sentiment(self, news_items: List[Dict]) -> Dict[str, Any]:
        """
        Analyze sentiment from CryptoPanic news votes.
        
        CryptoPanic provides sentiment via user votes:
        - positive, negative, important, liked, disliked, lol, toxic, saved, comments
        
        Returns:
            {
                score: float (-1 to 1),
                distribution: {positive: N, neutral: N, negative: N},
                confidence: float (0-1)
            }
        """
        if not news_items:
            return {
                "score": None,
                "distribution": None,
                "confidence": 0.0
            }
        
        total_positive = 0
        total_negative = 0
        total_neutral = 0
        
        for item in news_items:
            votes = item.get("votes", {})
            
            positive_votes = votes.get("positive", 0) + votes.get("liked", 0)
            negative_votes = votes.get("negative", 0) + votes.get("disliked", 0) + votes.get("toxic", 0)
            
            if positive_votes > negative_votes:
                total_positive += 1
            elif negative_votes > positive_votes:
                total_negative += 1
            else:
                total_neutral += 1
        
        total_items = len(news_items)
        
        # Calculate sentiment score (-1 to +1)
        if total_items > 0:
            score = (total_positive - total_negative) / total_items
        else:
            score = 0.0
        
        # Confidence based on sample size
        confidence = min(1.0, total_items / 20)  # Full confidence at 20+ articles
        
        return {
            "score": round(score, 3),
            "distribution": {
                "positive": total_positive,
                "neutral": total_neutral,
                "negative": total_negative
            },
            "confidence": round(confidence, 3)
        }
    
    def detect_attention_spike(
        self,
        current_count: int,
        baseline_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Detect if current attention is unusually high.
        
        Args:
            current_count: News count in recent period (e.g., 24h)
            baseline_count: Expected normal count (e.g., 7d average)
        
        Returns:
            {spike_detected: bool, percentile: float, evidence: str}
        """
        if baseline_count is None or baseline_count == 0:
            return {
                "spike_detected": False,
                "percentile": None,
                "evidence": "No baseline data available"
            }
        
        ratio = current_count / baseline_count
        
        # Spike if current is 2x baseline or more
        spike_detected = ratio >= 2.0
        
        # Estimate percentile (rough heuristic)
        if ratio >= 3.0:
            percentile = 0.95
        elif ratio >= 2.0:
            percentile = 0.90
        elif ratio >= 1.5:
            percentile = 0.75
        else:
            percentile = 0.50
        
        evidence = f"Current: {current_count} articles, Baseline: {baseline_count} articles, Ratio: {ratio:.2f}x"
        
        return {
            "spike_detected": spike_detected,
            "percentile": percentile,
            "evidence": evidence
        }
    
    def analyze_source_diversity(self, news_items: List[Dict]) -> Dict[str, Any]:
        """
        Measure source diversity to detect coordinated narratives.
        
        Low diversity = potential coordinated campaign.
        
        Returns:
            {diversity_score: float (0-1), unique_sources: int, total_articles: int}
        """
        if not news_items:
            return {
                "diversity_score": None,
                "unique_sources": 0,
                "total_articles": 0
            }
        
        sources = set()
        for item in news_items:
            source_domain = item.get("source", {}).get("domain")
            if source_domain:
                sources.add(source_domain)
        
        unique_sources = len(sources)
        total_articles = len(news_items)
        
        # Diversity = unique sources / total articles (closer to 1 = more diverse)
        diversity_score = unique_sources / total_articles if total_articles > 0 else 0
        
        return {
            "diversity_score": round(diversity_score, 3),
            "unique_sources": unique_sources,
            "total_articles": total_articles
        }
    
    def extract_narrative_keywords(self, news_items: List[Dict], top_n: int = 10) -> List[str]:
        """
        Extract most common keywords from news titles.
        Simple frequency-based extraction.
        """
        if not news_items:
            return []
        
        # Count word frequencies (excluding common words)
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "can", "this", "that", "these",
            "those", "i", "you", "he", "she", "it", "we", "they", "what", "which"
        }
        
        word_counts = {}
        
        for item in news_items:
            title = item.get("title", "").lower()
            words = title.split()
            
            for word in words:
                # Clean word
                word = word.strip(".,!?;:()[]{}\"'")
                if len(word) > 3 and word not in stop_words:
                    word_counts[word] = word_counts.get(word, 0) + 1
        
        # Sort by frequency
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [word for word, count in sorted_words[:top_n]]
