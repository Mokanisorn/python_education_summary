from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
import os
from datetime import datetime
import duckdb
from werkzeug.security import generate_password_hash, check_password_hash  # ✅ ใช้สำหรับ hashing password

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
except:
    pass

conn.close()

# ✅ ตรวจสอบการล็อกอินก่อนเข้าหน้าอื่น
@app.before_request
def check_session():
    if request.endpoint not in ['login', 'register', 'static', 'clear_session', 'index']:
        if 'user' not in session:
            flash("กรุณาเข้าสู่ระบบก่อนเข้าหน้านี้")
            return redirect(url_for('login'))

@app.route('/')
def index():
    # ✅ ล้าง session เก่าทุกครั้งเมื่อเข้าหน้าแรก
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

        if user and check_password_hash(user[2], password):  # ✅ ตรวจรหัสแบบ hash
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
            hashed_pw = generate_password_hash(password)  # ✅ แปลงเป็น hash ก่อนเก็บ
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

    data = conn.execute("SELECT * FROM posts ORDER BY timestamp DESC").fetchall()
    conn.close()

    posts = []
    for s in data:
        posts.append({
            'id': s[0],
            'user': s[1],
            'text': s[2],
            'file': s[3],
            'category': s[4],
            'category_display': category_names.get(s[4], s[4]) if s[4] else None,
            'category_class': s[4],
            'timestamp': s[5]
        })

    return render_template("index.html", posts=posts, comment_map={}, user=session["user"])

# ✅ รวม route วิชาไว้ในฟังก์ชันเดียว (ลดความซ้ำซ้อน)
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

@app.route("/logout")
def logout():
    session.clear()
    flash("ออกจากระบบสำเร็จ")
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(port=5002, debug=True)
