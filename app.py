from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, auth, storage
import pyrebase
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')  # Added default for development

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Pyrebase configuration
firebase_config = {
    "apiKey": os.getenv('FIREBASE_API_KEY'),
    "authDomain": os.getenv('FIREBASE_AUTH_DOMAIN'),
    "databaseURL": os.getenv('FIREBASE_DATABASE_URL'),
    "projectId": os.getenv('FIREBASE_PROJECT_ID'),
    "storageBucket": os.getenv('FIREBASE_STORAGE_BUCKET'),
    "messagingSenderId": os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    "appId": os.getenv('FIREBASE_APP_ID')
}

# Initialize Pyrebase
try:
    pb = pyrebase.initialize_app(firebase_config)
    auth_fb = pb.auth()
except Exception as e:
    print(f"❌ Pyrebase initialization error: {str(e)}")

# User model for Flask-Login
class User(UserMixin):
    def __init__(self, uid, email, token):
        self.id = uid
        self.email = email
        self.token = token

@login_manager.user_loader
def load_user(uid):
    if 'user' in session:
        user_data = session['user']
        return User(user_data['uid'], user_data['email'], user_data['token'])
    return None

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///plants.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Plant model
class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    soil_type = db.Column(db.String(100))
    sunlight_hours = db.Column(db.String(50))
    water_frequency = db.Column(db.String(100))
    fertilizer_type = db.Column(db.String(100))
    temperature = db.Column(db.String(50))
    humidity = db.Column(db.String(50))
    growth_milestone = db.Column(db.String(100))
    user_uid = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Initialize Firebase Admin
bucket = None
firebase_initialized = False

try:
    # Option 1: Use JSON file path (recommended)
    cred_path = os.path.join(os.path.dirname(__file__), 'firebase-key.json')
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        # Option 2: Use dictionary (make sure private key is properly formatted)
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": os.getenv('FIREBASE_PROJECT_ID'),
            "private_key": os.getenv('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
            "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
            "token_uri": "https://oauth2.googleapis.com/token"
        })
    
    firebase_admin.initialize_app(cred, {
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET')
    })
    bucket = storage.bucket()
    firebase_initialized = True
    print("✅ Firebase initialized successfully")
except Exception as e:
    print(f"❌ Firebase initialization error: {str(e)}")
    # Fallback to dummy storage
    class DummyBucket:
        def __init__(self):
            self.public_url = "/static/default-plant.jpg"
        def blob(self, *args, **kwargs):
            return self
        def upload_from_file(self, file, content_type=None):
            try:
                os.makedirs('local_uploads', exist_ok=True)
                filename = secure_filename(file.filename)
                save_path = os.path.join('local_uploads', filename)
                file.save(save_path)
                self.public_url = f"/local_uploads/{filename}"
                return True
            except Exception as e:
                print(f"❌ Local save failed: {str(e)}")
                raise RuntimeError("Both Firebase and local storage failed")
        def make_public(self):
            pass
    bucket = DummyBucket()

# Initialize database
with app.app_context():
    try:
        # Check if table exists and columns
        inspector = db.inspect(db.engine)
        if 'plant' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('plant')]
            
            # Add user_uid column if it doesn't exist
            if 'user_uid' not in columns:
                with db.engine.begin() as connection:
                    connection.execute(db.text(
                        'ALTER TABLE plant ADD COLUMN user_uid VARCHAR(100) NOT NULL DEFAULT "temp_user"'
                    ))
                print("✅ Added missing user_uid column")
                
            # Add created_at column if it doesn't exist
            if 'created_at' not in columns:
                with db.engine.begin() as connection:
                    connection.execute(db.text(
                        'ALTER TABLE plant ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                    ))
                print("✅ Added missing created_at column")
                
        db.create_all()
    except Exception as e:
        print(f"❌ Database error: {str(e)}")
        db.drop_all()
        db.create_all()
        print("✅ Recreated database tables")

# Plant database
PLANT_DATABASE = {
    'tomato': {
        'name': 'Tomato',
        'soil_type': 'Loamy Soil',
        'sunlight_hours': '6-8 hours',
        'water_frequency': 'Twice weekly',
        'fertilizer_type': 'Organic Compost',
        'temperature': '20-30°C',
        'humidity': '50-70%',
        'growth_milestone': 'Harvest in 60-80 days'
    },
    'chilli': {
        'name': 'Chilli',
        'soil_type': 'Well-drained Sandy Loam',
        'sunlight_hours': '6-10 hours',
        'water_frequency': 'When topsoil dry',
        'fertilizer_type': '5-10-10 NPK',
        'temperature': '20-30°C',
        'humidity': '40-60%',
        'growth_milestone': 'Fruits in 60-90 days'
    },
    'bellpepper': {
        'name': 'Bell Pepper',
        'soil_type': 'Well-drained Loam',
        'sunlight_hours': '6-8 hours', 
        'water_frequency': 'When topsoil dry',
        'fertilizer_type': '5-10-10 NPK',
        'temperature': '21-29°C',
        'humidity': '50-70%',
        'growth_milestone': 'Harvest in 60-75 days'
    },
    'strawberry': {
        'name': 'Strawberry',
        'soil_type': 'Acidic Soil (pH 5.5-6.5)',
        'sunlight_hours': '6-10 hours',
        'water_frequency': 'Daily light watering',
        'fertilizer_type': '10-10-10 Balanced',
        'temperature': '15-25°C',
        'humidity': '60-80%',
        'growth_milestone': 'Fruits in 60-90 days'
    }
}

DEFAULT_PLANT_INFO = {
    'name': 'Unknown Plant',
    'soil_type': 'N/A',
    'sunlight_hours': 'N/A',
    'water_frequency': 'N/A',
    'fertilizer_type': 'N/A',
    'temperature': 'N/A',
    'humidity': 'N/A',
    'growth_milestone': 'N/A'
}

def identify_plant(filename):
    """Flexible plant identification from filename"""
    base_name = secure_filename(filename).lower()
    
    # Map keywords to plant types
    plant_keywords = {
        'tomato': ['tomato', 'tomat'],
        'chilli': ['chilli', 'chili', 'chile'],
        'bellpepper': ['bellpepper', 'bell pepper', 'capsicum'],
        'strawberry': ['strawberry', 'strawberr']
    }
    
    # Check for each plant type
    for plant_id, keywords in plant_keywords.items():
        if any(keyword in base_name for keyword in keywords):
            return PLANT_DATABASE[plant_id]
    
    return DEFAULT_PLANT_INFO

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def firebase_upload(file, user_id):
    """Secure upload to Firebase Storage"""
    try:
        filename = secure_filename(file.filename)
        blob_path = f"users/{user_id}/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_file(file, content_type=file.content_type)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        raise RuntimeError(f"Upload failed: {str(e)}")

@app.context_processor
def inject_user():
    return {'current_user': current_user}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth_fb.sign_in_with_email_and_password(email, password)
            user_data = {
                'uid': user['localId'],
                'email': email,
                'token': user['idToken']
            }
            session['user'] = user_data
            login_user(User(user_data['uid'], email, user_data['token']))
            flash('Login successful!', 'success')
            return redirect(url_for('upload'))
        except Exception as e:
            flash(f'Login error: {str(e)}', 'error')
    return render_template('login.html', firebase_config=firebase_config)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth_fb.create_user_with_email_and_password(email, password)
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Signup error: {str(e)}', 'error')
    return render_template('signup.html')

@app.route('/google-login')
def google_login():
    token = request.args.get('token')
    try:
        user = auth.verify_id_token(token)
        user_data = {
            'uid': user['uid'],
            'email': user['email'],
            'token': token
        }
        session['user'] = user_data
        login_user(User(user_data['uid'], user_data['email'], token))
        flash('Login successful!', 'success')
        return redirect(url_for('upload'))
    except Exception as e:
        flash(f'Google login error: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'photo' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
            
        file = request.files['photo']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            try:
                user_uid = session['user']['uid']
                file_url = firebase_upload(file, user_uid)
                plant_info = identify_plant(file.filename)
                
                new_plant = Plant(
                    image_filename=secure_filename(file.filename),
                    image_url=file_url,
                    user_uid=user_uid,
                    **plant_info
                )
                
                db.session.add(new_plant)
                db.session.commit()
                
                return redirect(url_for('result', plant_id=new_plant.id))
            except Exception as e:
                flash(f'Error: {str(e)}', 'error')
        else:
            flash('Invalid file type', 'error')
    
    user_email = session['user']['email'] if 'user' in session else 'Guest'
    return render_template('upload.html', user_email=user_email)

@app.route('/result/<int:plant_id>')
@login_required
def result(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_uid != current_user.id:
        flash('You are not authorized to view this plant', 'error')
        return redirect(url_for('home'))
    
    return render_template('result.html', 
                         image=plant.image_filename,
                         plant_info={
                             'name': plant.name,
                             'soil_type': plant.soil_type,
                             'sunlight_hours': plant.sunlight_hours,
                             'water_frequency': plant.water_frequency,
                             'fertilizer_type': plant.fertilizer_type,
                             'temperature': plant.temperature,
                             'humidity': plant.humidity,
                             'growth_milestone': plant.growth_milestone
                         },
                         image_url=plant.image_url)

@app.route('/local_uploads/<filename>')
def serve_local_upload(filename):
    return send_from_directory('local_uploads', filename)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/history')
@login_required
def history():
    if not current_user.is_authenticated:
        flash('Please login to view your history', 'error')
        return redirect(url_for('login'))
        
    # Get all plants uploaded by the current user
    user_plants = Plant.query.filter_by(user_uid=current_user.id).order_by(Plant.id.desc()).all()
    return render_template('history.html', plants=user_plants)

if __name__ == '__main__':
    os.makedirs('local_uploads', exist_ok=True)
    app.run(ssl_context='adhoc', debug=True)