from sqlalchemy import Column, Integer, String, Enum
from database import Base

class Video(Base):
    __tablename__ = 'videos'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    url = Column(String(255))
    processed_url = Column(String(255))
    status = Column(Enum('pending', 'processing', 'completed', 'failed', name='status'), default='pending')

    def __repr__(self):
        return f"<Video(name='{self.name}', url='{self.url}', status='{self.status}')>"