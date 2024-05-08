import os, json, pika, sys
from sqlalchemy import create_engine
from google.cloud import storage
from google.oauth2 import service_account
from modelos.video import Video
from modelos.usuario import Usuario
from sqlalchemy.orm import  sessionmaker
from database import init_db, get_session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database

sys.path.append(os.path.join(os.path.dirname(__file__), 'modelos'))

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


gcp_credentials = {
    "type": os.environ.get("GCP_CREDENTIALS_TYPE", "service_account"),
    "project_id": os.environ.get("GCP_CREDENTIALS_PROJECT_ID", ),
    "private_key_id": os.environ.get("GCP_CREDENTIALS_PRIVATE_KEY_ID",),
    "private_key": str(os.environ.get("GCP_CREDENTIALS_PRIVATE_KEY")).replace('\\n', '\n'),
    "client_email": os.environ.get("GCP_CREDENTIALS_CLIENT_EMAIL"),
    "client_id": os.environ.get("GCP_CREDENTIALS_CLIENT_ID"),
    "auth_uri": os.environ.get("GCP_CREDENTIALS_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
    "token_uri": os.environ.get("GCP_CREDENTIALS_TOKEN_URI", "https://oauth2.googleapis.com/token"),
    "auth_provider_x509_cert_url": os.environ.get("GCP_CREDENTIALS_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
    "client_x509_cert_url": os.environ.get("GCP_CREDENTIALS_CLIENT_X509_CERT_URL"),
    "universe_domain": os.environ.get("GCP_CREDENTIALS_UNIVERSE_DOMAIN", "googleapis.com")
}

def get_engine(user, passwd, host, port, db):
    url = f"postgresql://{user}:{passwd}@{host}:{port}/{db}"
    if not database_exists(url):
        create_database(url)
    engine = create_engine(url, pool_size=50, echo=True)
    return engine

engine = get_engine(postgres_user, postgres_password, postgres_host, postgres_port, 'postgres')
init_db()

#Make sure the tmp folder exists
if not os.path.exists('/tmp'):
    os.makedirs('/tmp')


def file_processed(ch, method, properties, body):
    print('Received message:', body)
    message = json.loads(body)
    try:
        with get_session() as session:
            print('Updating video status to processing')
            video = session.query(Video).get(message['id'])
            if video is None:
                print('Video with id', message['id'], 'not found')
                return False
            print('Video found with filename:', video.name)
            video.status = 'processing'
            session.commit()
            print('Processing video')

            # Download video
            print('Downloading video')
            videoPath = f'/tmp/{message["filename"]}'
            with open(videoPath, 'wb') as f:
                f.write(download_blob('drones-app-storage', '', message['filename']))
            print('Video downloaded')

            # Process video
            #using shell command cut the video to 20 seconds
            os.system(f'ffmpeg -i {videoPath} -t 20 /tmp/short-{message["filename"]}')
            os.system(f'ffmpeg -i /tmp/short-{message["filename"]} -vf scale=1280:720 /tmp/aspect-{message["filename"]}')
            os.system(f'ffmpeg -i /tmp/aspect-{message["filename"]} -i logos/IDRL.png -filter_complex "[1:v]scale=200:-1[logo];[0:v][logo]overlay=10:10:enable=\'between(t,0,2)\'" /tmp/logo-{message["filename"]}')
            os.system(f'ffmpeg -i /tmp/logo-{message["filename"]} -i logos/IDRL.png -filter_complex "[1:v]scale=200:-1[logo];[0:v][logo]overlay=10:10:enable=\'between(t,18,20)\'" /tmp/processed-{message["filename"]}')

            print('Uploading processed video')

            upload_blob('drones-app-storage', f'/tmp/processed-{message["filename"]}', f'processed-{message["filename"]}')

            # Afher uploading the file to storage, we can delete the local files
            os.remove(f'/tmp/processed-{message["filename"]}')
            os.remove(f'/tmp/logo-{message["filename"]}')
            os.remove(f'/tmp/aspect-{message["filename"]}')
            os.remove(f'/tmp/short-{message["filename"]}')
            
            #copy to the nfs from /tmp/
            #os.system(f'cp /tmp/processed-{message["filename"]} /processed-{message["filename"]}')
            print('Processed video uploaded')
            video.processed_url = f'/processed-{message["filename"]}'
            video.status = 'completed'
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
        


def download_blob(bucket_name, source_folder, blob_name):
    storage_client = get_storage_client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_folder + blob_name)
    blob_bytes = blob.download_as_bytes()
    
    print("-> Downloaded storage object {} from bucket {}".format(blob_name, bucket_name))
    return blob_bytes

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    storage_client = get_storage_client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    generation_match_precondition = 0
    blob.upload_from_filename(source_file_name, if_generation_match = generation_match_precondition)

    print("\n-> Updaload storage object {} to bucket {} to {}".format(blob.name, bucket_name, destination_blob_name))

def get_storage_client():
    credentials = service_account.Credentials.from_service_account_info(gcp_credentials)
    return storage.Client(credentials=credentials)

channel.basic_consume(queue='files', on_message_callback=file_processed, auto_ack=False)

print(' [*] Waiting for messages. To exit press CTRL+C')
channel.start_consuming()