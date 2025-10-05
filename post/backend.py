from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
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
        file TEXT,
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
            flash("เข้าสู่ระบบสำเร็จ")
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
            flash("สมัครสมาชิกสำเร็จ")
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
        flash("เพิ่มสรุปแล้ว")
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

@app.route('/math')
def math():
    if "user" not in session:
        return redirect(url_for('login'))
    return render_template("math.html", user=session["user"])

@app.route('/physics')
def physics():
    if "user" not in session:
        return redirect(url_for('login'))
    return render_template("physics.html", user=session["user"])

@app.route('/biology')
def biology():
    if "user" not in session:
        return redirect(url_for('login'))
    return render_template("biology.html", user=session["user"])

@app.route('/chemistry')
def chemistry():
    if "user" not in session:
        return redirect(url_for('login'))
    return render_template("chemistry.html", user=session["user"])

@app.route('/history')
def history():
    if "user" not in session:
        return redirect(url_for('login'))
    return render_template("history.html", user=session["user"])

@app.route('/thai')
def thai():
    if "user" not in session:
        return redirect(url_for('login'))
    return render_template("thai.html", user=session["user"])

@app.route("/logout")
def logout():
    session.clear()
    flash("ออกจากระบบสำเร็จ")
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(port=5002, debug=True)