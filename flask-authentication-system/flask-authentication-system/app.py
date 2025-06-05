from flask import Flask, request, render_template, redirect, session, send_file
from flask_sqlalchemy import SQLAlchemy
import bcrypt
import cv2
import numpy as np
from werkzeug.utils import secure_filename
import os
from PIL import Image

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'  # SQLite database
app.config['UPLOAD_FOLDER'] = 'static/uploads'  # Folder to store uploaded images
app.secret_key = 'secret_key'  # Secret key for session management

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Model for User
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

    def __init__(self, email, password, name):
        self.name = name
        self.email = email
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))

# Create database tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        # Check if the email already exists
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error="Email already exists.")

        # Create a new user
        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check if the user exists
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['email'] = user.email
            return redirect('/dashboard')
        else:
            return render_template('login.html', error="Invalid email or password.")

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' in session:
        user = User.query.filter_by(email=session['email']).first()
        return render_template('dashboard.html', user=user)
    
    return redirect('/login')

@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect('/login')

# LSB Encoding Function
def encode_message(image_path, message, password=""):
    # Read the image using PIL
    try:
        img = Image.open(image_path)
        image = np.array(img)  # Convert to NumPy array for OpenCV compatibility
    except Exception as e:
        print(f"Error reading image: {e}")
        return None

    # Add password to the message (if provided)
    if password:
        message = f"{password}:{message}"

    # Convert the message to binary
    binary_message = ''.join(format(ord(char), '08b') for char in message) + '1111111111111110'  # End delimiter

    data_index = 0
    total_pixels = image.shape[0] * image.shape[1] * 3  # Total available pixels (R, G, B)

    # Check if the message is too large for the image
    if len(binary_message) > total_pixels:
        return None  # Message too large for image

    # Embed the message into the image
    for row in image:
        for pixel in row:
            for i in range(3):  # Modify R, G, B values
                if data_index < len(binary_message):
                    pixel[i] = (pixel[i] & 0xFE) | int(binary_message[data_index])
                    data_index += 1
                else:
                    break

    # Save the encoded image
    encoded_image_path = os.path.join(app.config['UPLOAD_FOLDER'], "encoded_image.png")
    Image.fromarray(image).save(encoded_image_path)  # Save using PIL
    return encoded_image_path

@app.route('/encode', methods=['GET', 'POST'])
def encode():
    if request.method == 'POST':
        if 'image' not in request.files:
            return render_template('encode.html', error="No image file uploaded.")

        image = request.files['image']
        message = request.form['message']
        password = request.form.get('password', '')  # Optional password

        if image.filename == '':
            return render_template('encode.html', error="No selected file.")

        # Save the uploaded image
        filename = secure_filename(image.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(image_path)

        # Encode the message into the image
        encoded_image_path = encode_message(image_path, message, password)

        if encoded_image_path:
            return send_file(os.path.abspath(encoded_image_path), as_attachment=True)
        else:
            return render_template('encode.html', error="Message too long for this image or invalid image file.")

    return render_template('encode.html')

# LSB Decoding Function
def decode_message(image_path, password=""):
    # Read the image using PIL
    try:
        img = Image.open(image_path)
        image = np.array(img)  # Convert to NumPy array for OpenCV compatibility
    except Exception as e:
        print(f"Error reading image: {e}")
        return None

    # Extract binary data from the image
    binary_data = ""
    for row in image:
        for pixel in row:
            for i in range(3):  # Extract R, G, B values
                binary_data += str(pixel[i] & 1)

    print(f"Binary data extracted: {binary_data[:100]}...")  # Debugging: Print first 100 bits

    # Convert binary data to message
    message_bits = [binary_data[i:i+8] for i in range(0, len(binary_data), 8)]
    message = ""
    for byte in message_bits:
        if byte == '1111111111111110':  # End delimiter
            break
        message += chr(int(byte, 2))

    print(f"Decoded message: {message}")  # Debugging: Print the decoded message

    # Handle password (if provided)
    if ":" in message:
        try:
            embedded_password, actual_message = message.split(":", 1)
            print(f"Embedded password: {embedded_password}, Provided password: {password}")  # Debugging
            if password and embedded_password == password:
                return actual_message
            elif password and embedded_password != password:
                return "Incorrect password"
            else:
                return "Password required"
        except ValueError:
            return "Invalid message format"
    else:
        return message  # No password was embedded

@app.route('/decode', methods=['GET', 'POST'])
def decode():
    if request.method == 'POST':
        if 'image' not in request.files:
            return render_template('encode.html', error="No image file uploaded.")

        image = request.files['image']
        password = request.form.get('password', '')  # Optional password

        if image.filename == '':
            return render_template('encode.html', error="No selected file.")

        # Save the uploaded image
        filename = secure_filename(image.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(image_path)

        print(f"Image saved at: {image_path}")  # Debugging: Print the image path

        # Decode the message from the image
        decoded_message = decode_message(image_path, password)

        if decoded_message:
            return render_template('encode.html', decoded_message=decoded_message)
        else:
            return render_template('encode.html', error="No message found or invalid image file.")

    return render_template('encode.html')

# Run the app
if __name__ == '__main__':
    app.run(debug=True)