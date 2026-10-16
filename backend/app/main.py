from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.db.session import init_db
from app.services.model_service import model_service
from app.utils.logging_config import logger

from app.api.routes.health import router as health_router
from app.api.routes.predictions import router as predictions_router
from app.api.routes.reports import router as reports_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.cities import router as cities_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    logger.info("Starting AquaSignal AI Waterlogging Early-Warning Backend...")
    try:
        init_db()
        logger.info("SQLite database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

    try:
        from app.db.mongodb import mongo_manager
        if mongo_manager.is_configured():
            logger.info("Attempting MongoDB Atlas initial connection...")
            if mongo_manager.connect():
                logger.info("MongoDB Atlas cluster initialized and ready.")
            else:
                logger.warning("MongoDB Atlas could not connect; operating on SQLite fallback.")
        else:
            logger.info("MongoDB Atlas URI is placeholder/unconfigured; operating on SQLite fallback.")
    except Exception as e:
        logger.error(f"Error during MongoDB initialization: {str(e)}")

    try:
        model_service.initialize_models()
    except Exception as e:
        logger.error(f"Error during model initialization: {str(e)}")

    yield

    # Shutdown:
    logger.info("Shutting down AquaSignal Backend.")
    try:
        from app.db.mongodb import mongo_manager
        mongo_manager.close()
    except Exception:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Early-warning monsoon hydrological intelligence and incident dispatch API for Mumbai and Pune.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom validation error handler for clean, client-friendly error responses
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join([str(x) for x in err.get("loc", [])])
        msg = err.get("msg", "Validation error")
        errors.append(f"{loc}: {msg}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": errors}
    )

import os
from fastapi.staticfiles import StaticFiles

# Ensure upload storage directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Include API Routers under /api
app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(predictions_router, prefix=settings.API_PREFIX)
app.include_router(reports_router, prefix=settings.API_PREFIX)
app.include_router(analytics_router, prefix=settings.API_PREFIX)
app.include_router(cities_router, prefix=settings.API_PREFIX)


# Also expose /health at root level for common developer and load-balancer probes
app.include_router(health_router)

@app.get("/", tags=["Root"])
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "health_check": f"{settings.API_PREFIX}/health",
        "supported_cities": list(model_service.models.keys()),
        "status": "operational",
    }
