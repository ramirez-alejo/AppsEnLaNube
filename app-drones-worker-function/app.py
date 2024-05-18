import base64
import os, json, sys
import functions_framework
from sqlalchemy import create_engine
from google.cloud import storage
from google.oauth2 import service_account
from video import Video
from usuario import Usuario
from sqlalchemy.orm import  sessionmaker
from database import init_db, get_session
from ffmpeg import FFmpeg
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database

sys.path.append(os.path.join(os.path.dirname(__file__), 'modelos'))


postgres_host = os.environ.get("POSTGRES_HOST", 'localhost')
postgres_port = os.environ.get("POSTGRES_PORT", '5432')
postgres_user = os.environ.get("POSTGRES_USER", 'postgres')
postgres_password = os.environ.get("POSTGRES_PASSWORD", 'postgres')


gcp_credentials = {
    "type": os.environ.get("GCP_CREDENTIALS_TYPE", "service_account"),
    "project_id": os.environ.get("GCP_CREDENTIALS_PROJECT_ID", "appsnube"),
    "private_key_id": os.environ.get("GCP_CREDENTIALS_PRIVATE_KEY_ID",""),
    "private_key": str(os.environ.get("GCP_CREDENTIALS_PRIVATE_KEY", "")).replace('\\n', '\n'),
    "client_email": os.environ.get("GCP_CREDENTIALS_CLIENT_EMAIL", ""),
    "client_id": os.environ.get("GCP_CREDENTIALS_CLIENT_ID", ""),
    "auth_uri": os.environ.get("GCP_CREDENTIALS_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
    "token_uri": os.environ.get("GCP_CREDENTIALS_TOKEN_URI", "https://oauth2.googleapis.com/token"),
    "auth_provider_x509_cert_url": os.environ.get("GCP_CREDENTIALS_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
    "client_x509_cert_url": os.environ.get("GCP_CREDENTIALS_CLIENT_X509_CERT_URL", ""),
    "universe_domain": os.environ.get("GCP_CREDENTIALS_UNIVERSE_DOMAIN", "googleapis.com")
}
credentials = service_account.Credentials.from_service_account_info(gcp_credentials)

def get_engine(user, passwd, host, port, db):
    url = f"postgresql://{user}:{passwd}@{host}:{port}/{db}"
    if not database_exists(url):
        create_database(url)
    engine = create_engine(url, pool_size=50, echo=True)
    return engine

#Make sure the tmp folder exists
if not os.path.exists('/tmp'):
    os.makedirs('/tmp')


@functions_framework.cloud_event
def process_file(cloud_event):
    body = base64.b64decode(cloud_event.data["message"]["data"])
    logging.warning('Received message: %s', body)
    engine = get_engine(postgres_user, postgres_password, postgres_host, postgres_port, 'postgres')
    init_db()
    #let's download the logo
    if not os.path.exists('/tmp/logo.png'):
        with open('/tmp/logo.png', 'wb') as f:
            f.write(download_blob('apps-nube', '', 'IDRL.png'))
    message = json.loads(body)
    logging.warning('MessageId: %s', message['id'])
    #parse message id as int
    message['id'] = int(message['id'])
    try:
        with get_session() as session:
            logging.warning('Updating video status to processing')
            video = session.query(Video).get(message['id'])
            if video is None:
                print('Video with id', message['id'], 'not found')
                return False
            logging.warning('Video found with filename:', video.name)
            video.status = 'processing'
            session.commit()
            logging.warning('Processing video')

            # Download video
            logging.warning('Downloading video')
            videoPath = f'/tmp/{message["filename"]}'
            with open(videoPath, 'wb') as f:
                f.write(download_blob('apps-nube', '', message['filename']))
            logging.warning('Video downloaded')

            # Process video
            ffmpeg = (
                FFmpeg()
                .input(videoPath)
                .output(f'/tmp/short-{message["filename"]}', t=20)
            )
            ffmpeg.execute()
            logging.warning('Short video created')
            ffmpeg = (
                FFmpeg()
                .input(f'/tmp/short-{message["filename"]}')
                .output(f'/tmp/aspect-{message["filename"]}', vf='scale=1280:720')
            )
            ffmpeg.execute()
            logging.warning('Aspect video created')

            ffmpeg = (
                FFmpeg()
                .input(f'/tmp/aspect-{message["filename"]}')
                .input('/tmp/logo.png')
                .option('filter_complex', '[1:v]scale=200:-1[logo];[0:v][logo]overlay=10:10:enable=\'between(t,0,2)\'')
                .output(f'/tmp/logo-{message["filename"]}')
            )
            ffmpeg.execute()
            
            logging.warning('Logo video created')
            ffmpeg = (
                FFmpeg()
                .input(f'/tmp/logo-{message["filename"]}')
                .input('/tmp/logo.png')
                .option('filter_complex', '[1:v]scale=200:-1[logo];[0:v][logo]overlay=10:10:enable=\'between(t,18,20)\'')
                .output(f'/tmp/processed-{message["filename"]}')
            )
            ffmpeg.execute()
            logging.warning('Uploading processed video')

            upload_blob('apps-nube', f'/tmp/processed-{message["filename"]}', f'processed-{message["filename"]}')

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
    return storage.Client(credentials=credentials)