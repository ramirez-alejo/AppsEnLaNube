import os, json, pika, sys
from sqlalchemy import create_engine
from azure.storage.blob import BlobServiceClient
from Modelos.video import Video
from sqlalchemy.orm import  sessionmaker
from database import init_db, get_session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database

sys.path.append(os.path.join(os.path.dirname(__file__), 'Modelos'))

rabbit_host = os.environ.get("RABBIT_HOST", 'localhost')
rabbit_port = os.environ.get("RABBIT_PORT", '5672')
rabbit_user = os.environ.get("RABBIT_USER", 'rabbitmq')
rabbit_password = os.environ.get("RABBIT_PASSWORD", 'rabbitmq')
connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host, port=rabbit_port, credentials=pika.PlainCredentials(rabbit_user, rabbit_password)))
channel = connection.channel()
channel.queue_declare(queue='files')



postgres_host = os.environ.get("POSTGRES_HOST", 'localhost')
postgres_port = os.environ.get("POSTGRES_PORT", '5432')
postgres_user = os.environ.get("POSTGRES_USER", 'postgres')
postgres_password = os.environ.get("POSTGRES_PASSWORD", 'postgres')


blob_account_connection_string = os.environ.get("BLOB_ACCOUNT_CONNECTION_STRING", 'DefaultEndpointsProtocol=https;AccountName=testingstoragealejandro;AccountKey=Cc0ow+VZ7ZarC357VZ8yEZWVoi6vW7iZ2l33shijZSR2j90bDVaEeKaULJKflTFROSaNRL2Sndfl+ASt6BQpjg==;EndpointSuffix=core.windows.net')
blob_container_name = os.environ.get("BLOB_CONTAINER_NAME", 'nube')
blob_service_client = BlobServiceClient.from_connection_string(blob_account_connection_string)
blob_container_client = blob_service_client.get_container_client(blob_container_name)

def get_engine(user, passwd, host, port, db):
    url = f"postgresql://{user}:{passwd}@{host}:{port}/{db}"
    if not database_exists(url):
        create_database(url)
    engine = create_engine(url, pool_size=50, echo=True)
    return engine

engine = get_engine(postgres_user, postgres_password, postgres_host, postgres_port, 'postgres')
init_db()


def file_processed(ch, method, properties, body):
    print('Received message:', body)
    message = json.loads(body)
    try:
        with get_session() as session:
            print('Downloading video from:', message['path'])
            """ blob_client = blob_container_client.get_blob_client(message['path'])
            with open(f'/tmp/{message["filename"]}', 'wb') as f:
                data = blob_client.download_blob()
                data.readinto(f) """
            print('Video downloaded')
            print('Updating video status to processing')
            video = session.query(Video).get(message['id'])
            if video is None:
                print('Video with id', message['id'], 'not found')
                return False
            print('Video found with filename:', video.name)
            video.status = 'processing'
            session.commit()
            print('Processing video')
            #TODO: Process video
            print('Video processed')
            video.status = 'completed'
            video.processed_url = 'Test URL'
            session.commit()
            print('Video updated')
        return True
    except Exception as e:
        print('Error:', e)
        video = session.query(Video).get(message['id'])
        if video:
            video.status = 'failed'
            session.commit()
        raise e
        


channel.basic_consume(queue='files', on_message_callback=file_processed, auto_ack=True)

print(' [*] Waiting for messages. To exit press CTRL+C')
channel.start_consuming()