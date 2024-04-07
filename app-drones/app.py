import os, uuid, json, pika, sys
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from azure.storage.blob import BlobServiceClient
from Modelos.usuario import Usuario
from Modelos.video import Video
from sqlalchemy.sql import text
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from database import init_db


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


engine = create_engine(f'postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/postgres')
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/postgres'
db = SQLAlchemy(app)

with app.app_context():
    init_db()
    migrate = Migrate(app, db)


@app.route('/health', methods=['GET'])
def salud_servicio():
     if hay_conexion_bd():
          return 'healthy'
     return 'unhealthy'


@app.route('/signup', methods=['POST'])
def signup():
    email = request.json.get('email')
    user = Usuario.query.filter_by(email=email).first()
    if user:
        return 'User already exists', 400
    user = Usuario()
    user.name = request.json.get('name')
    user.email = email
    user.password = request.json.get('password')
    db.session.add(user)
    db.session.commit()
    return 'User created', 201

@app.route('/login', methods=['POST'])
def login():
    email = request.json.get('email')
    user = Usuario.query.filter_by(email=email).first()
    if not user or user.password != request.json.get('password'):
        return 'Invalid credentials', 401
    return 'Login successful', 200

@app.route('/upload', methods=['POST'])
def upload():
    print('upload request with file:', request.files)    
    if 'video' not in request.files:
        return 'No file part in the request', 400
    file = request.files['video']
    # Updaload the file with a unique name
    file.filename = str(uuid.uuid4()) + secure_filename(file.filename)
    blob_client = blob_container_client.get_blob_client(file.filename)
    blob_client.upload_blob(file)
    #Insert the video entry in the db
    video = Video()
    video.name = file.filename
    video.url = blob_client.url
    video.status = 'pending'
    db.session.add(video)
    db.session.commit()
     # Create a json message with the file name and path
    message = json.dumps({"filename": file.filename, "path": blob_client.url, "id": video.id})
    channel.basic_publish(exchange='', routing_key='files', body=message)

    return 'Video file uploaded, id = ' + str(video.id), 201

@app.route('/videos', methods=['GET'])
def videos():
    videos = Video.query.all()
    return {'videos': [video.__repr__() for video in videos]}, 200

@app.route('/videos/<int:id>', methods=['GET'])
def video(id):
    video = Video.query.get(id)
    if not video:
        return 'Video with id ' + str(id) + ' not found', 404
    return video.__repr__(), 200

        
def hay_conexion_bd():
    valor = False
    try:
        db.session.execute(text("SELECT 1"))
        valor = True
    except Exception as e:
        print('Error en la conexión a la base de datos:', e)
        valor = False
    return valor
