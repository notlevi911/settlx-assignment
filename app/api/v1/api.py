"""
V1 API router - aggregates all v1 endpoints.
"""
from fastapi import APIRouter
from app.api.v1.endpoints import contract_truth, social_sentiment, liquidity_intel

api_router = APIRouter()

# Include all v1 endpoints
api_router.include_router(contract_truth.router, tags=["Contract Truth"])
api_router.include_router(social_sentiment.router, tags=["Social Intelligence"])
api_router.include_router(liquidity_intel.router, tags=["Liquidity Intelligence"])
