import time
from typing import Optional, Dict, Any
from pymongo import MongoClient, ASCENDING, DESCENDING, GEOSPHERE
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, PyMongoError

from app.config import settings
from app.utils.logging_config import logger

class MongoDBManager:
    """
    Manages MongoDB Atlas client connection, ping checks, collection access,
    and index initialization for AquaSignal AI.
    """
    _instance: Optional["MongoDBManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self._connected: bool = False
        self._connection_error: Optional[str] = None
        self._last_ping_latency_ms: Optional[float] = None
        self._initialized = True

    def is_placeholder_uri(self, uri: Optional[str]) -> bool:
        if not uri:
            return True
        placeholders = ["<USERNAME>", "<PASSWORD>", "<CLUSTER_HOST>", "USERNAME:PASSWORD", "<CLUSTER>"]
        return any(ph in uri for ph in placeholders)

    def is_configured(self) -> bool:
        return bool(settings.MONGODB_URI and not self.is_placeholder_uri(settings.MONGODB_URI))

    def connect(self) -> bool:
        """
        Attempts to connect to MongoDB Atlas using MONGODB_URI.
        If credentials contain placeholders or are invalid, returns False
        and preserves local SQLite fallback without raising unhandled exceptions.
        """
        if not self.is_configured():
            msg = (
                "MongoDB Atlas URI is not configured or contains placeholders (<USERNAME>/<PASSWORD>). "
                "Backend is operating with durable local SQLite database fallback."
            )
            self._connection_error = msg
            self._connected = False
            logger.info(msg)
            return False

        try:
            timeout_ms = getattr(settings, "MONGODB_TIMEOUT_MS", 5000)
            self.client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
                socketTimeoutMS=timeout_ms,
                appname="AquaSignal-Backend"
            )
            # Perform active ping to verify cluster reachability and authentication
            t0 = time.time()
            self.client.admin.command("ping")
            self._last_ping_latency_ms = round((time.time() - t0) * 1000, 2)

            db_name = getattr(settings, "MONGODB_DB_NAME", "aquasignal")
            self.db = self.client[db_name]
            self._connected = True
            self._connection_error = None
            logger.info(f"MongoDB Atlas connected successfully to database '{db_name}' (ping: {self._last_ping_latency_ms} ms)")

            # Initialize indexes
            self._ensure_indexes()
            return True

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self._connected = False
            self._connection_error = f"Atlas connection failed: {str(e)}"
            logger.warning(f"Could not reach MongoDB Atlas cluster: {str(e)}. Using SQLite fallback.")
            return False
        except PyMongoError as e:
            self._connected = False
            self._connection_error = f"MongoDB error: {str(e)}"
            logger.error(f"MongoDB Atlas error: {str(e)}. Using SQLite fallback.")
            return False
        except Exception as e:
            self._connected = False
            self._connection_error = f"Unexpected error connecting to MongoDB: {str(e)}"
            logger.error(f"Unexpected MongoDB connection error: {str(e)}")
            return False

    def ping(self) -> Dict[str, Any]:
        """
        Runs an active ping against MongoDB Atlas and returns latency and health summary.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "connected": False,
                "status": "unconfigured_or_placeholder",
                "database": getattr(settings, "MONGODB_DB_NAME", "aquasignal"),
                "ping_ms": None,
                "message": "MONGODB_URI in backend/.env contains unreplaced placeholders (<USERNAME>:<PASSWORD>). Please update it with your Atlas credentials.",
            }

        if not self.client or not self._connected:
            # Try connecting if not already connected
            success = self.connect()
            if not success:
                return {
                    "configured": True,
                    "connected": False,
                    "status": "connection_failed",
                    "database": getattr(settings, "MONGODB_DB_NAME", "aquasignal"),
                    "ping_ms": None,
                    "message": self._connection_error or "Failed to connect to MongoDB Atlas.",
                }

        try:
            t0 = time.time()
            self.client.admin.command("ping")
            latency_ms = round((time.time() - t0) * 1000, 2)
            self._last_ping_latency_ms = latency_ms
            self._connected = True
            return {
                "configured": True,
                "connected": True,
                "status": "active",
                "database": getattr(settings, "MONGODB_DB_NAME", "aquasignal"),
                "ping_ms": latency_ms,
                "message": "MongoDB Atlas connection is active and healthy.",
            }
        except Exception as e:
            self._connected = False
            self._connection_error = str(e)
            return {
                "configured": True,
                "connected": False,
                "status": "ping_failed",
                "database": getattr(settings, "MONGODB_DB_NAME", "aquasignal"),
                "ping_ms": None,
                "message": f"Ping failed: {str(e)}",
            }

    def _ensure_indexes(self):
        """Creates performant unique, sorting, and geospatial indexes."""
        if self.db is None:
            return
        try:
            reports_col = self.db["reports"]
            reports_col.create_index([("id", ASCENDING)], unique=True)
            reports_col.create_index([("city", ASCENDING), ("created_at", DESCENDING)])
            reports_col.create_index([("status", ASCENDING)])
            reports_col.create_index([("severity", ASCENDING)])
            # Geospatial 2dsphere index for location queries
            reports_col.create_index([("location", GEOSPHERE)])

            predictions_col = self.db["predictions"]
            predictions_col.create_index([("city", ASCENDING), ("created_at", DESCENDING)])
            predictions_col.create_index([("location_name", ASCENDING)])
            logger.info("MongoDB Atlas indexes ensured for 'reports' and 'predictions' collections.")
        except Exception as e:
            logger.warning(f"Warning creating MongoDB indexes: {str(e)}")

    def get_collection(self, name: str) -> Optional[Collection]:
        if not self._connected or self.db is None:
            # Try to connect once
            if self.is_configured() and not self.client:
                self.connect()
        if self._connected and self.db is not None:
            return self.db[name]
        return None

    def close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
            self.db = None
            self._connected = False

# Global singleton
mongo_manager = MongoDBManager()
