import logging
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorClient
from whatsapp_manager import WhatsAppServiceManager
from pause_service import ConversationPauseService
from instance_manager import InstanceManager
from cleanup_service import DataCleanupService
from database import get_database

logger = logging.getLogger(__name__)

async def get_instance_manager(db: AsyncIOMotorClient = Depends(get_database)) -> InstanceManager:
    """Provide an InstanceManager instance."""
    try:
        instance_manager = InstanceManager(db)
        logger.info("InstanceManager dependency initialized")
        return instance_manager
    except Exception as e:
        logger.error(f"Failed to initialize InstanceManager: {str(e)}")
        raise

async def get_pause_service(db: AsyncIOMotorClient = Depends(get_database)) -> ConversationPauseService:
    """Provide a ConversationPauseService instance."""
    try:
        pause_service = ConversationPauseService()
        await pause_service.initialize(db)
        logger.info("ConversationPauseService dependency initialized")
        return pause_service
    except Exception as e:
        logger.error(f"Failed to initialize ConversationPauseService: {str(e)}")
        raise

async def get_service_manager(
    db: AsyncIOMotorClient = Depends(get_database),
    pause_service: ConversationPauseService = Depends(get_pause_service),
    instance_manager: InstanceManager = Depends(get_instance_manager)
) -> WhatsAppServiceManager:
    """Provide a WhatsAppServiceManager instance."""
    try:
        service_manager = WhatsAppServiceManager(db, instance_manager, pause_service)
        logger.info("WhatsAppServiceManager dependency initialized")
        return service_manager
    except Exception as e:
        logger.error(f"Failed to initialize WhatsAppServiceManager: {str(e)}")
        raise

async def get_cleanup_service(
    service_manager: WhatsAppServiceManager = Depends(get_service_manager)
) -> DataCleanupService:
    """Provide a DataCleanupService instance."""
    try:
        cleanup_service = DataCleanupService(service_manager)
        logger.info("DataCleanupService dependency initialized")
        return cleanup_service
    except Exception as e:
        logger.error(f"Failed to initialize DataCleanupService: {str(e)}")
        raise