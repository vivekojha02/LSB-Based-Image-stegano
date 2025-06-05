from flask import Flask, render_template, request, send_file, jsonify
from PIL import Image
import io

app = Flask(__name__)

def text_to_bits(text):
    return ''.join(format(ord(char), '08b') for char in text)

def bits_to_text(bits):
    chars = [bits[i:i+8] for i in range(0, len(bits), 8)]
    return ''.join(chr(int(char, 2)) for char in chars)

def encode_lsb(image, message, password=""):
    message = password + ":" + message if password else message  # Embed password at the start of the message
    binary_message = text_to_bits(message) + '1111111111111110'  # End delimiter

    img = image.convert("RGB")
    pixels = img.load()

    width, height = img.size
    idx = 0

    for y in range(height):
        for x in range(width):
            if idx < len(binary_message):
                r, g, b = pixels[x, y]
                r = (r & ~1) | int(binary_message[idx])
                idx += 1
                if idx < len(binary_message):
                    g = (g & ~1) | int(binary_message[idx])
                    idx += 1
                if idx < len(binary_message):
                    b = (b & ~1) | int(binary_message[idx])
                    idx += 1
                pixels[x, y] = (r, g, b)
            else:
                break

    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output

def decode_lsb(image, password=""):
    img = image.convert("RGB")
    pixels = img.load()
    width, height = img.size
    bits = ""

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            bits += str(r & 1)
            bits += str(g & 1)
            bits += str(b & 1)

    message = bits_to_text(bits.split('1111111111111110')[0])
    if ":" in message:
        embedded_password, actual_message = message.split(":", 1)
        if password and embedded_password == password:
            return actual_message
        elif password and embedded_password != password:
            return "incorrect password"
        else:
            return "Password required"
    else:
        return message  # No password was embedded

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/encode', methods=['POST'])
def encode():
    image = Image.open(request.files['image'])
    message = request.form['message']
    password = request.form.get('password', "")
    encoded_image = encode_lsb(image, message, password)
    return send_file(encoded_image, mimetype='image/png', as_attachment=True, download_name="encoded_image.png")

@app.route('/decode', methods=['POST'])
def decode():
    image = Image.open(request.files['image'])
    password = request.form.get('password', "")
    decoded_message = decode_lsb(image, password)
    return jsonify(decoded_message)

if __name__ == '__main__':
    app.run(debug=True)
