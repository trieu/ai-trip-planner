# Import the factory from the internal module
from .data_service import DataServiceFactory

# Define what is accessible when someone imports * from services
__all__ = ["DataServiceFactory"]
