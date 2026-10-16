import pytest
import numpy as np
import pandas as pd
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db.session import Base, get_db
from app.db.models import ReportDB, PredictionDB  # noqa: F401
from app.services.model_service import model_service

# In-memory SQLite database for testing with StaticPool so all sessions share the same in-memory DB
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class MockModelDouble:
    """Test double implementing scikit-learn classifier interface."""
    def __init__(self, fixed_proba: float = 0.85):
        self.fixed_proba = fixed_proba
        self.feature_names_in_ = np.array([
            "rainfall_mm",
            "rainfall_intensity",
            "drainage_capacity_ratio",
            "elevation_m",
            "tide_level_m",
            "soil_saturation_index",
            "road_gradient_pct",
            "historical_incident_count",
        ])

    def predict_proba(self, X):
        n_samples = len(X)
        probs = []
        for _ in range(n_samples):
            probs.append([1.0 - self.fixed_proba, self.fixed_proba])
        return np.array(probs)

    def predict(self, X):
        return np.array([1 if self.fixed_proba >= 0.5 else 0])

class MockFailingModelDouble:
    """Test double that simulates an inference failure/exception."""
    def predict_proba(self, X):
        raise RuntimeError("Simulated matrix singularity or NaN error during inference.")

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(setup_test_db) -> Generator:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def client(setup_test_db) -> Generator[TestClient, None, None]:
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def mock_mumbai_model():
    """Injects a mock model into Mumbai's slot in model_service."""
    orig_model = model_service.models["Mumbai"].model
    orig_is_loaded = model_service.models["Mumbai"].is_loaded
    orig_has_proba = model_service.models["Mumbai"].has_predict_proba
    orig_features = model_service.models["Mumbai"].expected_features

    mock_obj = MockModelDouble(fixed_proba=0.85)
    model_service.models["Mumbai"].model = mock_obj
    model_service.models["Mumbai"].is_loaded = True
    model_service.models["Mumbai"].has_predict_proba = True
    model_service.models["Mumbai"].expected_features = list(mock_obj.feature_names_in_)

    yield mock_obj

    # Teardown: restore original state
    model_service.models["Mumbai"].model = orig_model
    model_service.models["Mumbai"].is_loaded = orig_is_loaded
    model_service.models["Mumbai"].has_predict_proba = orig_has_proba
    model_service.models["Mumbai"].expected_features = orig_features
