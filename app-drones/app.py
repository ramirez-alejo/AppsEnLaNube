import os, uuid, json, pika, sys
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from google.cloud import storage, pubsub_v1
from google.oauth2 import service_account
from modelos.usuario import Usuario
from modelos.video import Video
from sqlalchemy.sql import text
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from database import init_db
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import logging


sys.path.append(os.path.join(os.path.dirname(__file__), 'modelos'))


postgres_host = os.environ.get("POSTGRES_HOST", 'localhost')
postgres_port = os.environ.get("POSTGRES_PORT", '5432')
postgres_user = os.environ.get("POSTGRES_USER", 'postgres')
postgres_password = os.environ.get("POSTGRES_PASSWORD", 'postgres')


gcp_credentials = {
    "type": os.environ.get("GCP_CREDENTIALS_TYPE", "service_account"),
    "project_id": os.environ.get("GCP_CREDENTIALS_PROJECT_ID"),
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

credentials = service_account.Credentials.from_service_account_info(gcp_credentials)
publisher = pubsub_v1.PublisherClient(credentials=credentials)
topic_name = 'projects/{project_id}/topics/{topic}'.format(
    project_id=os.getenv('GCP_CREDENTIALS_PROJECT_ID'),
    topic='videos',
)

try:
    publisher.create_topic(name=topic_name)
except Exception as e:
    print('Error creating topic:', e)



engine = create_engine(f'postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/postgres', pool_size=400, max_overflow=0, echo=True)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/postgres'
db = SQLAlchemy(app)

with app.app_context():
    init_db()
    migrate = Migrate(app, db)


# Setup the Flask-JWT-Extended extension
app.config["JWT_SECRET_KEY"] = "super-secret"
jwt = JWTManager(app)



@app.route('/api/health', methods=['GET'])
def salud_servicio():
     if hay_conexion_bd():
          return 'healthy'
     return 'unhealthy'


@app.route('/api/auth/signup', methods=['POST'])
def signup():
    if not request.json.get('name') or not request.json.get('email') or not request.json.get('password1') or not request.json.get('password2'):
        return 'must provide name, email, password1 and password2', 400
    if request.json.get('password1') != request.json.get('password2'):
        return 'Passwords do not match', 400
    email = request.json.get('email')
    user = Usuario.query.filter_by(email=email).first()
    if user:
        return 'User already exists', 400
    user = Usuario()
    user.name = request.json.get('name')
    user.email = email
    user.password = request.json.get('password1')
    db.session.add(user)
    db.session.commit()
    return 'User created', 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    email = request.json.get('email')
    user = Usuario.query.filter_by(email=email).first()
    if not user or user.password != request.json.get('password'):
        return 'Invalid credentials', 401
    access_token = create_access_token(identity={"id": user.id, "name": user.name, "email": user.email})
    return jsonify(access_token=access_token)

@app.route('/api/tasks', methods=['POST'])
@jwt_required()
def upload():
    print('upload request with file:', request.files)    
    if 'video' not in request.files:
        return 'No file part in the request', 400
    current_user = get_jwt_identity()
    file = request.files['video']

    file.filename = str(uuid.uuid4()) + secure_filename(file.filename)
    file.save(file.filename)

    try:
        upload_blob('apps-nube', file.filename, file.filename)
    except Exception as e:
        print('Error uploading video to storage:', e)
        return str(e), 500
    
    # Afher uploading the file to storage, we can delete the local file
    os.remove(file.filename)
    #Insert the video entry in the db
    video = Video()
    video.name = file.filename
    video.url = file.filename
    video.status = 'pending'
    video.usuario = current_user['id']
    db.session.add(video)
    db.session.commit()
    message = json.dumps({"filename": file.filename, "path": video.url, "id": video.id})
    future = publisher.publish(topic_name, message.encode())
    future.result()
    return 'File uploaded, Created task with id = ' + str(video.id), 201

@app.route('/api/tasks', methods=['GET'])
@jwt_required()
def videos():
    current_user = get_jwt_identity()
    videos = Video.query.filter_by(usuario=current_user['id']).all()
    return {'tasks': [video.__repr__() for video in videos]}, 200


@app.route('/api/tasks/<int:id>', methods=['GET'])
@jwt_required()
def video(id):
    current_user = get_jwt_identity()
    video = Video.query.get(id)
    if not video or video.usuario != current_user['id']:
        return 'Task with id ' + str(id) + ' not found', 404
    return video.__repr__(), 200


@app.route('/api/tasks/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_video(id):
    current_user = get_jwt_identity()
    video = Video.query.get(id)
    if not video or video.usuario != current_user['id']:
        if video:
            print('Video found with id', video.id, 'and user', video.usuario)
        return 'Task with id ' + str(id) + ' not found', 404
    
    if video not in db.session:
        video = db.session.merge(video)

    db.session.delete(video)
    db.session.commit()
    return '', 200
        
def hay_conexion_bd():
    valor = False
    try:
        db.session.execute(text("SELECT 1"))
        valor = True
    except Exception as e:
        print('Error en la conexión a la base de datos:', e)
        valor = False
    return valor


def upload_blob(bucket_name, source_file_name, destination_blob_name):
    storage_client = get_storage_client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    generation_match_precondition = 0
    blob.upload_from_filename(source_file_name, if_generation_match = generation_match_precondition)

    print("\n-> Updaload storage object {} to bucket {} to {}".format(blob.name, bucket_name, destination_blob_name))

def get_storage_client():
    return storage.Client(credentials=credentials)

if __name__ == "__main__":
    app.run(host='0.0.0.0')

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()