"""
FastAPI application main entry point.
Defines all endpoints for the Token Due Diligence Decision Engine.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

# Import V1 API router
from app.api.v1.api import api_router as api_v1_router


# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="A truth machine for crypto token due diligence. Returns facts, signals, and explicit uncertainty.",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include V1 API routes
app.include_router(api_v1_router, prefix="/v1")


@app.get("/")
async def root():
    """Health check and API info."""
    return {
        "status": "operational",
        "service": settings.app_name,
        "version": "1.0.0",
        "philosophy": "PROVEN | INFERRED | UNKNOWN",
        "endpoints": {
            "contract_truth": "POST /v1/contracts/truth:analyze",
            "social_sentiment": "POST /v1/social/sentiment:score",
            "liquidity_intel": "POST /v1/liquidity/intel:snapshot"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": settings.app_name}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
