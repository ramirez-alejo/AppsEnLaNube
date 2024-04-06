from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os


postgres_host = os.environ.get("POSTGRES_HOST", 'localhost')
postgres_port = os.environ.get("POSTGRES_PORT", '5432')
postgres_user = os.environ.get("POSTGRES_USER", 'postgres')
postgres_password = os.environ.get("POSTGRES_PASSWORD", 'postgres')
engine = create_engine(f'postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/postgres')
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    # import all modules here that might define models so that
    # they will be registered properly on the metadata.  Otherwise
    # you will have to import them first before calling init_db()
    import Modelos.Usuario
    import Modelos.Video
    Base.metadata.create_all(bind=engine)