from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from flask_session import Session
import os
from datetime import datetime
import duckdb
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = 'brand_new_secret_key_xyz123'

# ตั้งค่า Session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_FILE_DIR'] = './flask_session'
Session(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# สร้างฐานข้อมูล DuckDB
DB_FILE = 'database.duckdb'
conn = duckdb.connect(DB_FILE)

# สร้าง SEQUENCE และตารางถ้ายังไม่มี
try:
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_users_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_posts_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_likes_id START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_comments_id START 1")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY DEFAULT nextval('seq_users_id'),
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id BIGINT PRIMARY KEY DEFAULT nextval('seq_posts_id'),
        user TEXT,
        text TEXT,
        category TEXT,
        timestamp TIMESTAMP
    )
    """)

    # ตาราง likes - 1 user กดได้ 1 ไลค์ต่อโพสต์
    conn.execute("""
    CREATE TABLE IF NOT EXISTS likes (
        id BIGINT PRIMARY KEY DEFAULT nextval('seq_likes_id'),
        post_id BIGINT,
        username TEXT,
        timestamp TIMESTAMP,
        UNIQUE(post_id, username)
    )
    """)

    # ตาราง comments - เก็บชื่อ user ที่คอมเมนต์
    conn.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id BIGINT PRIMARY KEY DEFAULT nextval('seq_comments_id'),
        post_id BIGINT,
        username TEXT,
        comment_text TEXT,
        timestamp TIMESTAMP
    )
    """)
except:
    pass

conn.close()

# ตรวจสอบการล็อกอินก่อนเข้าหน้าอื่น
@app.before_request
def check_session():
     if request.endpoint not in ['login', 'register', 'static', 'clear_session', 'index']:
        if 'user' not in session:
            flash("กรุณาเข้าสู่ระบบก่อนเข้าหน้านี้")
            return redirect(url_for('login'))

@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))

@app.route('/clear')
def clear_session():
    session.clear()
    flash("เคลียร์ session แล้ว")
    return redirect(url_for('login'))

@app.route('/api/delete_post/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'ไม่ได้ล็อกอิน'}), 401
    
    username = session['user']
    conn = duckdb.connect(DB_FILE)
    
    # ตรวจสอบว่าโพสต์เป็นของผู้ใช้หรือไม่
    post = conn.execute("SELECT user, file FROM posts WHERE id = ?", [post_id]).fetchone()
    
    if not post:
        conn.close()
        return jsonify({'success': False, 'error': 'ไม่พบโพสต์'}), 404
    
    if post[0] != username:
        conn.close()
        return jsonify({'success': False, 'error': 'คุณไม่มีสิทธิ์ลบโพสต์นี้'}), 403
    
    # ลบไฟล์ที่แนบมา (ถ้ามี)
    if post[1]:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], post[1])
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
    
    # ลบข้อมูลที่เกี่ยวข้องกับโพสต์
    conn.execute("DELETE FROM comments WHERE post_id = ?", [post_id])
    conn.execute("DELETE FROM likes WHERE post_id = ?", [post_id])
    conn.execute("DELETE FROM posts WHERE id = ?", [post_id])
    conn.close()
    
    return jsonify({'success': True})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = duckdb.connect(DB_FILE)
        user = conn.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session.clear()
            session['user'] = username
            return redirect(url_for('home'))
        else:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = duckdb.connect(DB_FILE)
        exists = conn.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()

        if exists:
            flash("ชื่อผู้ใช้ซ้ำ")
        else:
            hashed_pw = generate_password_hash(password)
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", [username, hashed_pw])
            conn.close()
            return redirect(url_for('login'))

        conn.close()

    return render_template('register.html')

@app.route('/home', methods=['GET', 'POST'])
def home():
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }

    conn = duckdb.connect(DB_FILE)

    if request.method == "POST":
        text = request.form.get("summary")
        category = request.form.get("category")
        file = request.files.get("file")
        file_filename = None

        if file and file.filename:
            file_filename = f"{int.from_bytes(os.urandom(8),'big')}_{file.filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_filename))

        conn.execute(
            "INSERT INTO posts (user, text, file, category, timestamp) VALUES (?, ?, ?, ?, ?)",
            [session['user'], text, file_filename, category, datetime.now()]
        )
        conn.close()
        return redirect(url_for('home'))

    # ดึงข้อมูล posts พร้อมกับข้อมูล likes และ comments
    data = conn.execute("SELECT * FROM posts ORDER BY timestamp DESC").fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        
        # นับจำนวนไลค์
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        
        # เช็คว่า user ปัจจุบันกดไลค์ไว้หรือยัง
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        
        # นับจำนวนคอมเมนต์
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]) if s[4] else None,
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })

    conn.close()

    return render_template("index.html", posts=posts, user=current_user)

# API: กดไลค์/เลิกไลค์
@app.route('/api/like/<int:post_id>', methods=['POST'])
def toggle_like(post_id):
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'ไม่ได้ล็อกอิน'}), 401
    
    username = session['user']
    conn = duckdb.connect(DB_FILE)
    
    # เช็คว่ากดไลค์ไว้แล้วหรือยัง
    existing = conn.execute("SELECT * FROM likes WHERE post_id = ? AND username = ?", 
                           [post_id, username]).fetchone()
    
    if existing:
        # ถ้ากดไว้แล้ว ให้เลิกไลค์
        conn.execute("DELETE FROM likes WHERE post_id = ? AND username = ?", [post_id, username])
        liked = False
    else:
        # ถ้ายังไม่กด ให้เพิ่มไลค์
        conn.execute("INSERT INTO likes (post_id, username, timestamp) VALUES (?, ?, ?)",
                    [post_id, username, datetime.now()])
        liked = True
    
    # นับจำนวนไลค์ใหม่
    like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
    conn.close()
    
    return jsonify({'success': True, 'liked': liked, 'like_count': like_count})

# API: ดึงคอมเมนต์ทั้งหมดของโพสต์
@app.route('/api/comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    conn = duckdb.connect(DB_FILE)
    comments = conn.execute(
        "SELECT username, comment_text, timestamp FROM comments WHERE post_id = ? ORDER BY timestamp ASC",
        [post_id]
    ).fetchall()
    conn.close()
    
    result = [{
        'username': c[0],
        'text': c[1],
        'timestamp': c[2].isoformat() if c[2] else None
    } for c in comments]
    
    return jsonify({'success': True, 'comments': result})

# API: เพิ่มคอมเมนต์ใหม่
@app.route('/api/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'ไม่ได้ล็อกอิน'}), 401
    
    data = request.get_json()
    comment_text = data.get('text', '').strip()
    
    if not comment_text:
        return jsonify({'success': False, 'error': 'ข้อความว่างเปล่า'}), 400
    
    username = session['user']
    conn = duckdb.connect(DB_FILE)
    
    # เพิ่มคอมเมนต์ลง database
    conn.execute(
        "INSERT INTO comments (post_id, username, comment_text, timestamp) VALUES (?, ?, ?, ?)",
        [post_id, username, comment_text, datetime.now()]
    )
    
    # นับจำนวนคอมเมนต์ใหม่
    comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
    conn.close()
    
    return jsonify({
        'success': True, 
        'username': username,
        'text': comment_text,
        'comment_count': comment_count
    })

@app.route('/subject/<category>')
def subject_page(category):
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }

    conn = duckdb.connect(DB_FILE)
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", [category]).fetchall()
    conn.close()

    posts = [{
        'id': s[0],
        'user': s[1],
        'text': s[2],
        'file': s[3],
        'category': s[4],
        'category_display': category_names.get(s[4], s[4]),
        'category_class': s[4],
        'timestamp': s[5]
    } for s in data]

    return render_template('subject.html', posts=posts, category_display=category_names.get(category), user=session.get('user'))

@app.route('/sub')
def sub():
    return render_template('subject.html', user=session.get('user'))

@app.route('/set')
def set():
    return render_template('set.html', user=session.get('user'))

@app.route('/math')
def math():
    if "user" not in session:
        return redirect(url_for('login'))
    
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }
    
    conn = duckdb.connect(DB_FILE)
    # ดึงเฉพาะโพสต์ที่เป็นหมวดหมู่ math
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", ['math']).fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]),
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })
    
    conn.close()
    return render_template("math.html", posts=posts, user=current_user)

@app.route('/physics')
def physics():
    if "user" not in session:
        return redirect(url_for('login'))
    
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }
    
    conn = duckdb.connect(DB_FILE)
    # ดึงเฉพาะโพสต์ที่เป็นหมวดหมู่ math
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", ['physics']).fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]),
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })
    
    conn.close()
    return render_template("physics.html", posts=posts, user=current_user)

@app.route('/biology')
def biology():
    if "user" not in session:
        return redirect(url_for('login'))
    
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }
    
    conn = duckdb.connect(DB_FILE)
    # ดึงเฉพาะโพสต์ที่เป็นหมวดหมู่ math
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", ['biology']).fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]),
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })
    
    conn.close()
    return render_template("biology.html", posts=posts, user=current_user)

@app.route('/chemistry')
def chemistry():
    if "user" not in session:
        return redirect(url_for('login'))
    
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }
    
    conn = duckdb.connect(DB_FILE)
    # ดึงเฉพาะโพสต์ที่เป็นหมวดหมู่ math
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", ['chemistry']).fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]),
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })
    
    conn.close()
    return render_template("chemistry.html", posts=posts, user=current_user)

@app.route('/history')
def history():
    if "user" not in session:
        return redirect(url_for('login'))
    
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }
    
    conn = duckdb.connect(DB_FILE)
    # ดึงเฉพาะโพสต์ที่เป็นหมวดหมู่ math
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", ['history']).fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]),
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })
    
    conn.close()
    return render_template("history.html", posts=posts, user=current_user)

@app.route('/thai')
def thai():
    if "user" not in session:
        return redirect(url_for('login'))
    
    category_names = {
        'math': 'คณิตศาสตร์',
        'physics': 'ฟิสิกส์',
        'biology': 'ชีววิทยา',
        'chemistry': 'เคมี',
        'history': 'ประวัติศาสตร์',
        'thai': 'ภาษาไทย'
    }
    
    conn = duckdb.connect(DB_FILE)
    # ดึงเฉพาะโพสต์ที่เป็นหมวดหมู่ math
    data = conn.execute("SELECT * FROM posts WHERE category = ? ORDER BY timestamp DESC", ['thai']).fetchall()
    
    posts = []
    current_user = session['user']
    
    for s in data:
        post_id = s[0]
        like_count = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", [post_id]).fetchone()[0]
        user_liked = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ? AND username = ?", 
                                   [post_id, current_user]).fetchone()[0] > 0
        comment_count = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", [post_id]).fetchone()[0]
        
        posts.append({
            'id': post_id,
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]),
            'category_class': s[4],
            'timestamp': s[5],
            'like_count': like_count,
            'user_liked': user_liked,
            'comment_count': comment_count
        })
    
    conn.close()
    return render_template("thai.html", posts=posts, user=current_user)

@app.route('/setting', methods=['GET', 'POST'])
def setting():
    if 'user' not in session:
        flash("กรุณาเข้าสู่ระบบก่อนเข้าหน้านี้")
        return redirect(url_for('login'))
    
    current_username = session['user']
    conn = duckdb.connect(DB_FILE)
    
    if request.method == 'POST':
        new_username = request.form.get('new_username', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # ดึงข้อมูลผู้ใช้ปัจจุบัน
        user = conn.execute("SELECT * FROM users WHERE username = ?", [current_username]).fetchone()
        
        if not user:
            flash("ไม่พบข้อมูลผู้ใช้")
            conn.close()
            return redirect(url_for('set'))
        
        # ตรวจสอบรหัสผ่านปัจจุบัน
        if not check_password_hash(user[2], current_password):
            flash("รหัสผ่านปัจจุบันไม่ถูกต้อง")
            conn.close()
            response = make_response(render_template('set.html', user=current_username, current_username=current_username))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        # ตรวจสอบรหัสผ่านใหม่ตรงกันหรือไม่
        if new_password != confirm_password:
            flash("รหัสผ่านใหม่ไม่ตรงกัน")
            conn.close()
            response = make_response(render_template('set.html', user=current_username, current_username=current_username))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        # ตรวจสอบว่าชื่อผู้ใช้ใหม่ซ้ำกับคนอื่นหรือไม่
        if new_username != current_username:
            existing = conn.execute("SELECT * FROM users WHERE username = ?", [new_username]).fetchone()
            if existing:
                flash("ชื่อผู้ใช้นี้มีคนใช้แล้ว")
                conn.close()
                response = make_response(render_template('set.html', user=current_username, current_username=current_username))
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                return response
        
        # อัปเดตข้อมูล
        hashed_pw = generate_password_hash(new_password)
        
        try:
            # อัปเดต username และ password
            conn.execute("UPDATE users SET username = ?, password = ? WHERE username = ?", 
                        [new_username, hashed_pw, current_username])
            
            # อัปเดต username ในตาราง posts
            conn.execute("UPDATE posts SET user = ? WHERE user = ?", 
                        [new_username, current_username])
            
            # อัปเดต username ในตาราง likes
            conn.execute("UPDATE likes SET username = ? WHERE username = ?", 
                        [new_username, current_username])
            
            # อัปเดต username ในตาราง comments
            conn.execute("UPDATE comments SET username = ? WHERE username = ?", 
                        [new_username, current_username])
            
            # อัปเดต session
            session['user'] = new_username
            
            flash("อัปเดตข้อมูลสำเร็จ")
            conn.close()
            return redirect(url_for('set'))
            
        except Exception as e:
            flash(f"เกิดข้อผิดพลาด: {str(e)}")
            conn.close()
            return redirect(url_for('set'))
    
    conn.close()
    response = make_response(render_template('setting.html', user=current_username, current_username=current_username))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route("/logout")
def logout():
    session.clear()
    response = make_response(redirect(url_for('login')))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)