import os, uuid, json, pika, sys
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from azure.storage.blob import BlobServiceClient
from modelos.usuario import Usuario
from modelos.video import Video
from sqlalchemy.sql import text
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from database import init_db
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity


sys.path.append(os.path.join(os.path.dirname(__file__), 'modelos'))


rabbit_host = os.environ.get("RABBIT_HOST", 'localhost')
rabbit_port = os.environ.get("RABBIT_PORT", '5672')
rabbit_user = os.environ.get("RABBIT_USER", 'rabbitmq')
rabbit_password = os.environ.get("RABBIT_PASSWORD", 'rabbitmq')


postgres_host = os.environ.get("POSTGRES_HOST", 'localhost')
postgres_port = os.environ.get("POSTGRES_PORT", '5432')
postgres_user = os.environ.get("POSTGRES_USER", 'postgres')
postgres_password = os.environ.get("POSTGRES_PASSWORD", 'postgres')



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

connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host, port=rabbit_port, credentials=pika.PlainCredentials(rabbit_user, rabbit_password)))
channel = connection.channel()
channel.queue_declare(queue='files')
channel.close()
connection.close()


def get_rabbit_connection():
    global connection
    try:
        if connection.is_closed:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host, port=rabbit_port, credentials=pika.PlainCredentials(rabbit_user, rabbit_password), heartbeat=600))
    except (NameError, pika.exceptions.ConnectionClosed):
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host, port=rabbit_port, credentials=pika.PlainCredentials(rabbit_user, rabbit_password), heartbeat=600))
    return connection

def get_rabbit_channel():
    global channel
    connection = get_rabbit_connection()
    try:
        if channel.is_closed:
            channel = connection.channel()
    except (NameError, pika.exceptions.ConnectionClosed):
        channel = connection.channel()
    return channel


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
    file.save('/nfsshare/' + file.filename)
    
    #Insert the video entry in the db
    video = Video()
    video.name = file.filename
    video.url = '/nfsshare/' + file.filename
    video.status = 'pending'
    video.usuario = current_user['id']
    db.session.add(video)
    db.session.commit()
     # Create a json message with the file name and path
    message = json.dumps({"filename": file.filename, "path": video.url, "id": video.id})
    with get_rabbit_channel() as channel:
        channel.basic_publish(exchange='', routing_key='files', body=message)


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



@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()