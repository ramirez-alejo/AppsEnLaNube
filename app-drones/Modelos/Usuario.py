from sqlalchemy import Column, Integer, String
from database import Base

class Usuario(Base):
    __tablename__ = 'usuarios'

    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    email = Column(String(100), unique=True)
    password = Column(String(100))

    def __repr__(self):
        return f"<Usuario(nombre='{self.name}', email='{self.email}')>"