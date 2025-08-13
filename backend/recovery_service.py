import asyncio
import time
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from evolution_api import Client as EvolutionClient, EvolutionAPIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WhatsAppRecoveryService:
    def __init__(self):
        self.mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.evolution_api_url = os.environ.get('EVOLUTION_API_URL')
        self.evolution_api_key = os.environ.get('EVOLUTION_API_KEY')
        if not self.evolution_api_url or not self.evolution_api_key:
            logger.error("EVOLUTION_API_URL or EVOLUTION_API_KEY environment variable not set")
            raise ValueError("EVOLUTION_API_URL and EVOLUTION_API_KEY are required")
        self.client = AsyncIOMotorClient(self.mongo_url)
        self.db = self.client[os.environ.get('DB_NAME', 'whatsapp_assistant')]
        self.api_client = EvolutionClient(api_key=self.evolution_api_key, base_url=self.evolution_api_url)
        self.running = True
        logger.info("WhatsAppRecoveryService initialized")

    async def get_active_clients(self):
        """Obtain active clients from the database"""
        try:
            clients = await self.db.clients.find({"status": "active"}).to_list(length=None)
            logger.debug(f"Found {len(clients)} active clients")
            return clients
        except Exception as e:
            logger.error(f"Error fetching active clients: {str(e)}")
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def check_service_health(self, client_id: str) -> bool:
        """Check if an Evolution API instance is responding and connected"""
        try:
            status_data = await self.api_client.fetch_instance(client_id)
            return status_data.get('instance', {}).get('state') == 'connected'
        except EvolutionAPIError as e:
            logger.error(f"Error checking Evolution API health for {client_id[:8]}: {str(e)}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def restart_service(self, client_id: str) -> bool:
        """Restart a client's service using Evolution API"""
        try:
            logger.info(f"Attempting to disconnect Evolution API instance: {client_id[:8]}")
            try:
                await self.api_client.disconnect(client_id)
                logger.info(f"Instance {client_id[:8]} disconnected successfully")
            except EvolutionAPIError as e:
                if "instance not found" in str(e).lower():
                    logger.warning(f"Instance {client_id[:8]} not found, proceeding to connect")
                else:
                    logger.error(f"Error disconnecting {client_id[:8]}: {str(e)}")

            await asyncio.sleep(5)  # Give time for disconnection

            logger.info(f"Attempting to connect Evolution API instance: {client_id[:8]}")
            await self.api_client.connect(client_id, qrcode=True)
            logger.info(f"Service {client_id[:8]} restarted successfully")
            return True
        except EvolutionAPIError as e:
            logger.error(f"Error restarting {client_id[:8]}: {str(e)}")
            return False

    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("🔄 Starting WhatsApp Recovery Service")
        
        while self.running:
            try:
                # Get active clients
                active_clients = await self.get_active_clients()
                logger.info(f"📊 Monitoring {len(active_clients)} active clients")
                
                for client in active_clients:
                    client_id = client['id']
                    client_name = client['name']
                    
                    # Check service health
                    if not await self.check_service_health(client_id):
                        logger.warning(f"⚠️ Service {client_name} (ID: {client_id[:8]}) is not connected or not responding")
                        
                        # Attempt restart
                        if await self.restart_service(client_id):
                            logger.info(f"🔄 Waiting for initialization of {client_name}...")
                            await asyncio.sleep(45)  # Time for initialization
                        else:
                            logger.error(f"❌ Failed to restart {client_name}")
                    else:
                        # Check if QR code is needed
                        try:
                            status_data = await self.api_client.fetch_instance(client_id)
                            instance_state = status_data.get('instance', {}).get('state')
                            if instance_state in ['qrCode', 'disconnected']:
                                logger.info(f"🔄 {client_name} (ID: {client_id[:8]}) needs QR or is disconnected, forcing restart...")
                                await self.restart_service(client_id)
                        except EvolutionAPIError as e:
                            logger.error(f"Error checking QR for {client_name} (ID: {client_id[:8]}): {str(e)}")
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(60)  # Wait longer if error occurs
    
    def stop(self):
        """Stop the recovery service"""
        self.running = False
        self.client.close()
        logger.info("🛑 Recovery service stopped")

async def start_recovery_service():
    """Start the recovery service"""
    recovery = WhatsAppRecoveryService()
    try:
        await recovery.monitor_loop()
    except KeyboardInterrupt:
        recovery.stop()
        logger.info("👋 Recovery service terminated")

if __name__ == "__main__":
    asyncio.run(start_recovery_service())