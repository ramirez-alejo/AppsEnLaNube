import datetime
from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime
from database import Base

class Video(Base):
    __tablename__ = 'videos'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    url = Column(String(255))
    processed_url = Column(String(255))
    status = Column( Enum('pending', 'processing', 'completed', 'failed', name='status'), default='pending')
    usuario = Column(Integer, ForeignKey('usuarios.id'))
    created = Column(DateTime, default=datetime.datetime.now)


    def __repr__(self):
        return f"Video(id='{self.id}', name='{self.name}', url='{self.url}', status='{self.status}, created='{self.created}')"