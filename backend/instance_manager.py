import os
import logging
from fastapi import HTTPException
from evolution_api import Client as EvolutionClient, EvolutionAPIError  # Use evolution_api to align with WhatsAppServiceManager
from motor.motor_asyncio import AsyncIOMotorClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import PyMongoError
from threading import Lock
from cachetools import LRUCache

logger = logging.getLogger(__name__)

class InstanceManager:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.evolution_api_url = os.environ.get("EVOLUTION_API_URL")
        self.evolution_api_key = os.environ.get("EVOLUTION_API_KEY")
        if not self.evolution_api_url or not self.evolution_api_key:
            logger.error("EVOLUTION_API_URL or EVOLUTION_API_KEY environment variable not set")
            raise ValueError("EVOLUTION_API_URL and EVOLUTION_API_KEY are required")
        # Thread-safe LRU cache with max size
        self.client_cache = LRUCache(maxsize=100)
        self.cache_lock = Lock()
        logger.info("InstanceManager initialized")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def get_client(self, client_id: str) -> EvolutionClient:
        """Retrieve or create an EvolutionClient for a given client_id."""
        with self.cache_lock:
            if client_id in self.client_cache:
                logger.debug(f"Returning cached EvolutionClient for client {client_id}")
                return self.client_cache[client_id]

        try:
            config = await self.db.clients.find_one({"client_id": client_id})
            if not config:
                logger.error(f"Client {client_id} not found in database")
                raise HTTPException(status_code=404, detail=f"Client {client_id} not found")

            try:
                client = EvolutionClient(
                    base_url=self.evolution_api_url,
                    api_key=config.get("instance_token", self.evolution_api_key)
                )
                with self.cache_lock:
                    self.client_cache[client_id] = client
                logger.info(f"Created new EvolutionClient for client {client_id}")
                return client
            except EvolutionAPIError as e:
                logger.error(f"Failed to initialize EvolutionClient for client {client_id}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to initialize Evolution API client: {str(e)}")
        except PyMongoError as e:
            logger.error(f"Database error fetching config for client {client_id}: {str(e)}")
            raise

    async def clear_cache(self, client_id: str = None):
        """Clear the client cache for a specific client_id or all clients."""
        with self.cache_lock:
            if client_id:
                self.client_cache.pop(client_id, None)
                logger.info(f"Cleared cache for client {client_id}")
            else:
                self.client_cache.clear()
                logger.info("Cleared entire client cache")