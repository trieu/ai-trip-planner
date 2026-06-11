import logging
from typing import List, Optional, Any

# Assuming python-arango is used for typing the database connection
from arango.database import StandardDatabase 

from backend.services.data_models.ag_profile import CDP_PROFILE_QUERY, ArangoProfile

logger = logging.getLogger(__name__)

class ArangoProfileRepository:
    """
    Repository class to interact with ArangoDB and load validated ArangoProfile models.
    """
    
    def __init__(self, db: StandardDatabase, batch_size: int = 1000):
        """
        Initialize the repository.
        
        Args:
            db: The active python-arango StandardDatabase instance.
            batch_size: Default batch size for queries (can be overridden in fetch).
        """
        self.db = db
        self.batch_size = batch_size

    def resolve_segment_id(self, segment_name: str) -> Optional[str]:
        """
        Looks up a segment ID by its name in the cdp_segment collection.
        Returns the most populated active segment if multiple match.
        """
        query = """
        FOR s IN cdp_segment
            FILTER s.name == @name AND s.status == 1
            SORT s.totalCount DESC
            LIMIT 1
            RETURN s._key
        """
        try:
            cursor = self.db.aql.execute(query, bind_vars={"name": segment_name})
            return next(iter(cursor), None)
        except Exception as e:
            logger.error("[ArangoDB] Failed to resolve segment name %s: %s", segment_name, e)
            return None

    def fetch_profiles_by_segment(
        self, 
        segment_id: Optional[str] = None, 
        segment_name: Optional[str] = None, 
        start_index: int = 0, 
        batch_size: int = 100
    ) -> List[ArangoProfile]:
        """
        Fetches profiles from ArangoDB matching a segment ID or Name, 
        and maps them into verified ArangoProfile Pydantic objects.
        """
        # Resolve segment_id if only segment_name is provided
        if not segment_id and segment_name:
            segment_id = self.resolve_segment_id(segment_name)
            logger.info(
                "[ArangoDB] Resolving segment ID for name '%s' -> '%s'",
                segment_name,
                segment_id,
            )

        # Abort if no valid segment ID could be found
        if not segment_id:
            logger.warning("[ArangoDB] Segment not found or could not be resolved for: %s", segment_name)
            return []

        bind_vars = {
            "segment_id": segment_id,
            "start_index": start_index,
            "batch_size": batch_size
        }

        profiles: List[ArangoProfile] = []
        
        try:
            # Execute the AQL query
            cursor = self.db.aql.execute(
                CDP_PROFILE_QUERY,
                bind_vars=bind_vars
            )

            # Iterate through the cursor and parse into the Pydantic model
            for doc in cursor:
                try:
                    profiles.append(ArangoProfile.from_arango(doc))
                except Exception as e:
                    # Log mapping issues but continue processing the batch
                    logger.error(f"[ArangoDB] Failed to parse profile document: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"[ArangoDB] Failed to execute profile query for segment {segment_id}: {e}")

        return profiles


# =====================================================
# Example usage:
# =====================================================
# from arango import ArangoClient
# client = ArangoClient(hosts="http://localhost:8529")
# db = client.db("my_database", username="root", password="password")
# repo = ArangoProfileRepository(db)
# 
# # Fetching by ID
# segment_profiles = repo.fetch_profiles_by_segment(segment_id="3sbeyPZV9WEKO9UaNiWtAC", start_index=0, batch_size=50)
# for profile in segment_profiles:
#     print(profile.profile_id, profile.primaryEmail)
#
# # Fetching by Name
# segment_profiles_by_name = repo.fetch_profiles_by_segment(segment_name="Active Visitor Profile")
# for profile in segment_profiles_by_name:
#     print(profile.profile_id, profile.primaryPhone)