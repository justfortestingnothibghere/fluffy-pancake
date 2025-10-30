import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, Response
from werkzeug.utils import secure_filename
from models import db, User, Video, Like, Comment

app = Flask(__name__)
app.config['SECRET_KEY'] = 'e3ed3ed9829ceff4dba8984ab3997c0a'  # Change this to a random secret
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

with app.app_context():
    db.create_all()

# Helper to check if logged in
def is_logged_in():
    return 'user_id' in session

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return 'Username taken'
        user = User(username=username, password=password)  # In production, hash password!
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()  # Hash in prod!
        if user:
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            return redirect(url_for('index'))
        return 'Invalid credentials'
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Home - List videos
@app.route('/')
def index():
    videos = Video.query.all()
    return render_template('index.html', videos=videos, is_logged_in=is_logged_in())

# Upload video
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not is_logged_in():
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        file = request.files['file']
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            video = Video(title=title, filename=filename, uploader_id=session['user_id'])
            db.session.add(video)
            db.session.commit()
            return redirect(url_for('index'))
    return render_template('upload.html')

# View video (shareable link)
@app.route('/video/<int:video_id>')
def video(video_id):
    vid = Video.query.get_or_404(video_id)
    user_vote = None
    like_count = sum(1 for l in vid.likes if l.vote == 1)
    unlike_count = sum(1 for l in vid.likes if l.vote == -1)
    if is_logged_in():
        user_vote = Like.query.filter_by(user_id=session['user_id'], video_id=video_id).first()
    comments = Comment.query.filter_by(video_id=video_id).all()
    return render_template('video.html', video=vid, like_count=like_count, unlike_count=unlike_count,
                           user_vote=user_vote, comments=comments, is_logged_in=is_logged_in())

# Serve video file with streaming
@app.route('/uploads/<filename>')
def serve_video(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
    size = os.path.getsize(path)
    byte1, byte2 = 0, None
    m = re.fullmatch(r'bytes=([0-9]+)-([0-9]+)?', range_header)
    if m:
        byte1 = int(m.group(1))
        if m.group(2):
            byte2 = int(m.group(2))
    
    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1 + 1
    
    with open(path, 'rb') as f:
        f.seek(byte1)
        data = f.read(length)
    
    resp = Response(data, 206, mimetype='video/mp4', content_type='video/mp4', direct_passthrough=True)
    resp.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{size}')
    return resp

# Like video
@app.route('/like/<int:video_id>', methods=['POST'])
def like(video_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    existing = Like.query.filter_by(user_id=session['user_id'], video_id=video_id).first()
    if existing:
        existing.vote = 1
    else:
        like = Like(user_id=session['user_id'], video_id=video_id, vote=1)
        db.session.add(like)
    db.session.commit()
    return redirect(url_for('video', video_id=video_id))

# Unlike video
@app.route('/unlike/<int:video_id>', methods=['POST'])
def unlike(video_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    existing = Like.query.filter_by(user_id=session['user_id'], video_id=video_id).first()
    if existing:
        existing.vote = -1
    else:
        like = Like(user_id=session['user_id'], video_id=video_id, vote=-1)
        db.session.add(like)
    db.session.commit()
    return redirect(url_for('video', video_id=video_id))

# Comment on video
@app.route('/comment/<int:video_id>', methods=['POST'])
def comment(video_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    text = request.form['text']
    if text:
        comm = Comment(user_id=session['user_id'], video_id=video_id, text=text)
        db.session.add(comm)
        db.session.commit()
    return redirect(url_for('video', video_id=video_id))

# Admin panel
@app.route('/admin')
def admin():
    if not (is_logged_in() and session.get('is_admin')):
        return 'Access denied'
    videos = Video.query.all()
    return render_template('admin.html', videos=videos)

# Delete video (admin only)
@app.route('/delete/<int:video_id>')
def delete(video_id):
    if not (is_logged_in() and session.get('is_admin')):
        return 'Access denied'
    vid = Video.query.get_or_404(video_id)
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], vid.filename))
    db.session.delete(vid)
    db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
