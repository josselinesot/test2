from flask import Flask, render_template, request, session, redirect, url_for, flash, send_file
from pymongo import MongoClient
import bcrypt
from io import BytesIO
from datetime import datetime
import gridfs
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "advpjsh"

# Configuración de la base de datos
client = MongoClient("mongodb+srv://jossy:kaiser2510@joss.gk5bacg.mongodb.net/?retryWrites=true&w=majority&appName=Joss")
db = client['db1']
users = db.users
fs = gridfs.GridFS(db)

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return redirect(url_for('prin'))

@app.route('/prin')
def prin():
    return render_template('prin.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')
        
        admin_user = users.find_one({'username': 'admin'})
        if admin_user and (admin_user['email'] == username or admin_user['username'] == username) and bcrypt.checkpw(password, admin_user['password']):
            flash('No puedes iniciar sesión como administrador en el portal de usuario.', 'error')
            return redirect(url_for('login'))
        
        user = users.find_one({'$or': [{'username': username}, {'email': username}]})
        if user and bcrypt.checkpw(password, user['password']):
            session['username'] = user['username']
            return redirect(url_for('home'))
        else:
            flash('Datos incorrectos. Por favor, verifica tu usuario, correo o contraseña.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        existing_user = users.find_one({'username': request.form['username']})
        if existing_user is None:
            hashpass = bcrypt.hashpw(request.form['password'].encode('utf-8'), bcrypt.gensalt())
            users.insert_one({
                'username': request.form['username'],
                'password': hashpass,
                'email': request.form['email'],
                'fullname': request.form['fullname'],
                'phone': request.form['phone']
            })
            session['username'] = request.form['username']
            return redirect(url_for('home'))
        flash('El usuario ya existe. Por favor, elige un nombre de usuario diferente.', 'error')
    return render_template('register.html')

@app.route('/home')
def home():
    if 'username' in session:
        user_pdfs = get_user_pdfs(session['username'])
        return render_template('home.html', username=session['username'], user_pdfs=user_pdfs)
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'username' in session:
        if 'pdf_file' not in request.files or 'description' not in request.form or 'year' not in request.form:
            flash('No se encontró el archivo PDF, la descripción o el año.', 'error')
            return redirect(url_for('home'))

        file = request.files['pdf_file']
        description = request.form['description']
        year = request.form['year']
        if file.filename == '':
            flash('No se seleccionó ningún archivo.', 'error')
            return redirect(url_for('home'))

        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            file_data = file.read()
            upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Guardar el archivo PDF en GridFS
            file_id = fs.put(file_data, filename=filename, metadata={
                'description': description,
                'year': year,
                'upload_time': upload_time
            })

            # Guardar la información del PDF en la base de datos del usuario
            users.update_one(
                {'username': session['username']},
                {'$push': {'pdfs': {'file_id': file_id, 'filename': filename, 'description': description, 'year': year, 'upload_time': upload_time}}}
            )

            flash('Archivo subido con éxito.', 'success')
            return redirect(url_for(f'user_events_{year}', username=session['username']))
        else:
            flash('Solo se permiten archivos PDF.', 'error')
            return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')
        admin_user = users.find_one({'username': 'admin'})
        if admin_user and admin_user['email'] == username and bcrypt.checkpw(password, admin_user['password']):
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Datos incorrectos. Por favor, verifica tu correo o contraseña.', 'error')
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    all_users = users.find({}, {'username': 1, 'pdfs': 1})
    user_pdfs_grouped = {}
    for user in all_users:
        username = user['username']
        pdfs = user.get('pdfs', [])
        user_pdfs_grouped[username] = pdfs

    return render_template('admin_dashboard.html', user_pdfs_grouped=user_pdfs_grouped)

@app.route('/admin/user/<username>')
def admin_user_dashboard(username):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    user = users.find_one({'username': username})
    if user:
        user_files = user.get('pdfs', [])
        return render_template('admin_user_dashboard.html', username=username, user_files=user_files)
    return render_template('admin_user_dashboard.html', username=username, user_files=[])

@app.route('/admin/user_pdfs/<username>')
def admin_user_pdfs(username):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    user = users.find_one({'username': username})
    if user:
        user_files = user.get('pdfs', [])
        return render_template('admin_user_pdfs.html', username=username, user_files=user_files)
    return render_template('admin_user_pdfs.html', username=username, user_files=[])

@app.route('/download_pdf/<file_id>')
def download_pdf(file_id):
    if 'username' in session or 'admin' in session:
        file = fs.find_one({'_id': ObjectId(file_id)})
        if file:
            return send_file(
                BytesIO(file.read()),
                as_attachment=True,
                download_name=file.filename
            )
        else:
            flash('Archivo no encontrado en la base de datos.', 'error')
    return redirect(url_for('home'))

@app.route('/delete_pdf/<file_id>', methods=['POST'])
def delete_pdf(file_id):
    if 'username' not in session and 'admin' not in session:
        return redirect(url_for('login'))

    if not ObjectId.is_valid(file_id):
        flash('ID de archivo inválido', 'danger')
        return redirect(url_for('home'))

    try:
        # Encuentra el archivo antes de eliminarlo
        file = fs.find_one({'_id': ObjectId(file_id)})
        if file:
            # Elimina el archivo de GridFS
            fs.delete(ObjectId(file_id))
            # Elimina el archivo de la base de datos del usuario
            users.update_many(
                {'pdfs.file_id': ObjectId(file_id)},
                {'$pull': {'pdfs': {'file_id': ObjectId(file_id)}}}
            )
            flash('Archivo eliminado con éxito', 'success')
        else:
            flash('Archivo no encontrado', 'danger')
    except gridfs.errors.NoFile:
        flash('Archivo no encontrado', 'danger')

    return redirect(url_for('home'))

@app.route('/admin/events/2022/<username>')
def admin_events_2022(username):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    user = users.find_one({'username': username})
    if user:
        user_files = [pdf for pdf in user.get('pdfs', []) if pdf.get('year') == '2022']
        return render_template('admin_events_2022.html', username=username, user_files=user_files)
    
    return render_template('admin_events_2022.html', username=username, user_files=[])

@app.route('/user/events/2022/<username>')
def user_events_2022(username):
    if 'username' in session:
        user = users.find_one({'username': session['username']})
        if user:
            user_pdfs = [pdf for pdf in user.get('pdfs', []) if pdf.get('year') == '2022']
            return render_template('2022.html', username=session['username'], user_pdfs=user_pdfs)
    
    return redirect(url_for('login'))

@app.route('/admin/events/2023/<username>')
def admin_events_2023(username):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    user = users.find_one({'username': username})
    if user:
        user_files = [pdf for pdf in user.get('pdfs', []) if pdf.get('year') == '2023']
        return render_template('admin_events_2023.html', username=username, user_files=user_files)
    
    return render_template('admin_events_2023.html', username=username, user_files=[])

@app.route('/user/events/2023/<username>')
def user_events_2023(username):
    if 'username' in session:
        user = users.find_one({'username': session['username']})
        if user:
            user_pdfs = [pdf for pdf in user.get('pdfs', []) if pdf.get('year') == '2023']
            return render_template('2023.html', username=session['username'], user_pdfs=user_pdfs)
    
    return redirect(url_for('login'))

@app.route('/admin/events/2024/<username>')
def admin_events_2024(username):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    user = users.find_one({'username': username})
    if user:
        user_files = [pdf for pdf in user.get('pdfs', []) if pdf.get('year') == '2024']
        return render_template('admin_events_2024.html', username=username, user_files=user_files)
    
    return render_template('admin_events_2024.html', username=username, user_files=[])

@app.route('/user/events/2024/<username>')
def user_events_2024(username):
    if 'username' in session:
        user = users.find_one({'username': session['username']})
        if user:
            user_pdfs = [pdf for pdf in user.get('pdfs', []) if pdf.get('year') == '2024']
            return render_template('2024.html', username=session['username'], user_pdfs=user_pdfs)
    
    return redirect(url_for('login'))

@app.route('/search', methods=['GET'])
def search_pdfs():
    if 'username' in session:
        query = request.args.get('query', '').strip()
        user_pdfs = get_user_pdfs(session['username'])
        filtered_pdfs = [pdf for pdf in user_pdfs if query.lower() in pdf['filename'].lower()]
        return render_template('home.html', username=session['username'], user_pdfs=filtered_pdfs)
    
    return redirect(url_for('login'))

def get_user_pdfs(username):
    user = users.find_one({'username': username})
    return user.get('pdfs', [])

if __name__ == "__main__":
    app.run(debug=True)
