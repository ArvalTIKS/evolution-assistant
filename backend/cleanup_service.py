import asyncio
from datetime import datetime, timedelta
from database import get_database_direct
import logging
import os

logger = logging.getLogger(__name__)

class DataCleanupService:
    def __init__(self):
        # Cleanup interval for the scheduler (how often it runs)
        self.cleanup_interval_seconds = int(os.environ.get('CLEANUP_INTERVAL_HOURS', 24)) * 60 * 60
        
        # Retention periods for different data types
        self.message_retention_days = int(os.environ.get('MESSAGE_RETENTION_DAYS', 30)) # Default 30 days
        self.thread_retention_days = int(os.environ.get('THREAD_RETENTION_DAYS', 90))  # Default 90 days
        self.client_message_retention_days = int(os.environ.get('CLIENT_MESSAGE_RETENTION_DAYS', 30)) # Default 30 days

        self.running = False
    
    async def start_cleanup_scheduler(self):
        """Start the automated cleanup scheduler"""
        self.running = True
        logger.info(f"🧹 Data cleanup scheduler started - running every {self.cleanup_interval_seconds / 3600} hours")
        
        while self.running:
            try:
                # Wait for the configured interval
                await asyncio.sleep(self.cleanup_interval_seconds)
                
                if self.running:  # Check if still running after sleep
                    await self.run_cleanup()
                    
            except asyncio.CancelledError:
                logger.info("Cleanup scheduler cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup scheduler: {str(e)}")
                # Continue running even if one cleanup fails, wait a bit before next attempt
                await asyncio.sleep(3600) # Wait 1 hour before retrying after an error
    
    async def run_cleanup(self):
        """Run the cleanup process"""
        try:
            logger.info("🧹 Starting automated data cleanup...")
            
            # Get database connection
            db = await get_database_direct()
            
            # Calculate cutoff times based on retention days
            message_cutoff_time = datetime.utcnow() - timedelta(days=self.message_retention_days)
            thread_cutoff_time = datetime.utcnow() - timedelta(days=self.thread_retention_days)
            client_message_cutoff_time = datetime.utcnow() - timedelta(days=self.client_message_retention_days)

            logger.info(f"Cleaning WhatsApp messages older than: {message_cutoff_time} ({self.message_retention_days} days)")
            logger.info(f"Cleaning WhatsApp threads older than: {thread_cutoff_time} ({self.thread_retention_days} days)")
            logger.info(f"Cleaning Client messages older than: {client_message_cutoff_time} ({self.client_message_retention_days} days)")

            # Clean client messages (assuming this collection is still relevant)
            client_messages_deleted = await self._cleanup_client_messages(db, client_message_cutoff_time)
            
            # Clean WhatsApp threads (now includes instance_id)
            whatsapp_threads_deleted = await self._cleanup_whatsapp_threads(db, thread_cutoff_time)
            
            # Clean WhatsApp messages (now includes instance_id)
            whatsapp_messages_deleted = await self._cleanup_whatsapp_messages(db, message_cutoff_time)
            
            logger.info(f"✅ Cleanup completed successfully:")
            logger.info(f"   - Client messages deleted: {client_messages_deleted}")
            logger.info(f"   - WhatsApp threads cleaned: {whatsapp_threads_deleted}")
            logger.info(f"   - WhatsApp messages deleted: {whatsapp_messages_deleted}")
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {str(e)}")
    
    async def _cleanup_client_messages(self, db, cutoff_time: datetime) -> int:
        """Clean old client messages (assuming this collection is still used elsewhere)"""
        try:
            client_messages_collection = db.client_messages
            result = await client_messages_collection.delete_many({
                "created_at": {"$lt": cutoff_time}
            })
            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} old client messages")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning client messages: {str(e)}")
            return 0
    
    async def _cleanup_whatsapp_threads(self, db, cutoff_time: datetime) -> int:
        """Clean old WhatsApp conversation threads (now includes instance_id)"""
        try:
            whatsapp_threads_collection = db.whatsapp_threads # Corrected collection name
            result = await whatsapp_threads_collection.delete_many({
                "last_used": {"$lt": cutoff_time} # Assuming last_used is updated in whatsapp_routes
            })
            deleted_count = result.deleted_count
            logger.info(f"Deleted {deleted_count} old WhatsApp threads")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning WhatsApp threads: {str(e)}")
            return 0
    
    async def _cleanup_whatsapp_messages(self, db, cutoff_time: datetime) -> int:
        """Clean old WhatsApp messages (now includes instance_id)"""
        try:
            whatsapp_messages_collection = db.whatsapp_messages
            result = await whatsapp_messages_collection.delete_many({
                "created_at": {"$lt": cutoff_time}
            })
            deleted_count = result.deleted_count
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old WhatsApp messages")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning WhatsApp messages: {str(e)}")
            return 0
    
    async def force_cleanup(self):
        """Force immediate cleanup (for testing/manual trigger)"""
        logger.info("🧹 Force cleanup triggered")
        await self.run_cleanup()
    
    def stop_cleanup_scheduler(self):
        """Stop the cleanup scheduler"""
        self.running = False
        logger.info("Cleanup scheduler stopped")

# Global cleanup service instance
cleanup_service = DataCleanupService()

async def start_cleanup_service():
    """Start the cleanup service in background"""
    asyncio.create_task(cleanup_service.start_cleanup_scheduler())
