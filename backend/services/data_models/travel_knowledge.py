from sqlalchemy import Column, Text, JSON, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector
import uuid

Base = declarative_base()


class TravelKnowledge(Base):
    __tablename__ = "travel_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    destination = Column(Text)
    category = Column(Text)
    content = Column(Text)
    source = Column(Text)
    embedding = Column(Vector(1536))

    meta = Column("metadata", JSON)

    created_at = Column(TIMESTAMP, server_default=func.now())