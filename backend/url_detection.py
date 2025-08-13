import os
import logging
from urllib.parse import urlparse, ParseResult

# Configure logging
logger = logging.getLogger(__name__)

def validate_url(url: str) -> bool:
    """Validate if a URL is properly formatted."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def get_backend_base_url() -> str:
    """
    Get the backend base URL with multiple fallbacks for different environments
    Priority order:
    1. DEPLOYMENT_URL (production deployment)
    2. PREVIEW_ENDPOINT (preview environment) 
    3. BASE_URL (configured base URL)
    4. Development fallback
    """
    # Priority 1: Production deployment URL
    deployment_url = os.environ.get('DEPLOYMENT_URL', '').strip()
    if deployment_url and validate_url(deployment_url):
        logger.info(f"Using DEPLOYMENT_URL: {deployment_url}")
        return deployment_url
    elif deployment_url:
        logger.warning(f"Invalid DEPLOYMENT_URL: {deployment_url}")

    # Priority 2: Preview environment URL  
    preview_endpoint = os.environ.get('PREVIEW_ENDPOINT', '').strip()
    if preview_endpoint and validate_url(preview_endpoint):
        logger.info(f"Using PREVIEW_ENDPOINT: {preview_endpoint}")
        return preview_endpoint
    elif preview_endpoint:
        logger.warning(f"Invalid PREVIEW_ENDPOINT: {preview_endpoint}")

    # Priority 3: Base URL fallback
    base_url = os.environ.get('BASE_URL', '').strip()
    if base_url and validate_url(base_url):
        logger.info(f"Using BASE_URL: {base_url}")
        return base_url
    elif base_url:
        logger.warning(f"Invalid BASE_URL: {base_url}")

    # Priority 4: Development fallback
    dev_url = "http://host.docker.internal:8000"
    logger.info(f"Using DEVELOPMENT fallback: {dev_url}")
    return dev_url

def get_frontend_base_url() -> str:
    """
    Get the frontend base URL for email links and redirects
    Same priority system as backend
    """
    # Priority 1: Production deployment URL
    deployment_url = os.environ.get('DEPLOYMENT_URL', '').strip()
    if deployment_url and validate_url(deployment_url):
        logger.info(f"Frontend using DEPLOYMENT_URL: {deployment_url}")
        return deployment_url
    elif deployment_url:
        logger.warning(f"Invalid DEPLOYMENT_URL: {deployment_url}")

    # Priority 2: Preview environment URL
    preview_endpoint = os.environ.get('PREVIEW_ENDPOINT', '').strip() 
    if preview_endpoint and validate_url(preview_endpoint):
        logger.info(f"Frontend using PREVIEW_ENDPOINT: {preview_endpoint}")
        return preview_endpoint
    elif preview_endpoint:
        logger.warning(f"Invalid PREVIEW_ENDPOINT: {preview_endpoint}")

    # Priority 3: Frontend Base URL
    frontend_base_url = os.environ.get('FRONTEND_BASE_URL', '').strip()
    if frontend_base_url and validate_url(frontend_base_url):
        logger.info(f"Frontend using FRONTEND_BASE_URL: {frontend_base_url}")
        return frontend_base_url
    elif frontend_base_url:
        logger.warning(f"Invalid FRONTEND_BASE_URL: {frontend_base_url}")

    # Priority 4: Development fallback  
    dev_url = "http://localhost:5173"
    logger.info(f"Frontend using DEVELOPMENT fallback: {dev_url}")
    return dev_url

def detect_environment() -> str:
    """
    Detect which environment we're running in based on URLs
    Returns: 'production', 'preview', or 'development'
    """
    deployment_url = os.environ.get('DEPLOYMENT_URL', '').strip()
    if deployment_url and validate_url(deployment_url) and '.emergent.host' in deployment_url:
        return 'production'
        
    preview_endpoint = os.environ.get('PREVIEW_ENDPOINT', '').strip()
    if preview_endpoint and validate_url(preview_endpoint) and '.preview.emergentagent.com' in preview_endpoint:
        return 'preview'
        
    base_url = os.environ.get('BASE_URL', '').strip()
    if base_url and validate_url(base_url) and 'emergent' in base_url:
        if '.emergent.host' in base_url:
            return 'production'
        elif '.preview.emergentagent.com' in base_url:
            return 'preview'
    
    return 'development'

def get_environment_info() -> dict:
    """
    Get comprehensive environment information for debugging
    """
    env = detect_environment()
    backend_url = get_backend_base_url()
    frontend_url = get_frontend_base_url()
    
    return {
        'environment': env,
        'backend_url': backend_url,
        'frontend_url': frontend_url,
        'deployment_url': os.environ.get('DEPLOYMENT_URL', ''),
        'preview_endpoint': os.environ.get('PREVIEW_ENDPOINT', ''),
        'base_url': os.environ.get('BASE_URL', ''),
        'fallback_used': backend_url == "http://host.docker.internal:8000"
    }

# Initialize logging on import
logger.info("URL detection module loaded")
env_info = get_environment_info()
logger.info(f"Environment detected: {env_info}")