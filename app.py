import os, csv, io
from datetime import date, datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE-ME-BEFORE-DEPLOYMENT")

def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL sozlanmagan. PostgreSQL ulanishini kiriting.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg.connect(url, row_factory=dict_row)

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('superadmin','admin')),
            created_at TIMESTAMP NOT NULL DEFAULT NOW())""")
        con.execute("""CREATE TABLE IF NOT EXISTS students (
            id BIGSERIAL PRIMARY KEY, student_code TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL, group_name TEXT DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT NOW())""")
        con.execute("""CREATE TABLE IF NOT EXISTS attendance (
            id BIGSERIAL PRIMARY KEY, student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            attendance_date DATE NOT NULL, lesson TEXT DEFAULT '',
            status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late')),
            marked_by TEXT DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(student_id, attendance_date, lesson))""")
        con.execute("""CREATE TABLE IF NOT EXISTS telegram_links (
            id BIGSERIAL PRIMARY KEY, student_id BIGINT UNIQUE NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            telegram_id BIGINT UNIQUE NOT NULL, linked_at TIMESTAMP NOT NULL DEFAULT NOW())""")
        count = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            con.execute("INSERT INTO users(username,password_hash,role) VALUES(%s,%s,%s)",
                ("admin", generate_password_hash(os.environ.get("INITIAL_SUPERADMIN_PASSWORD","ChangeMe123!")), "superadmin"))
            con.execute("INSERT INTO users(username,password_hash,role) VALUES(%s,%s,%s)",
                ("operator", generate_password_hash(os.environ.get("INITIAL_ADMIN_PASSWORD","Operator123!")), "admin"))

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"): return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles: abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco

@app.route("/")
def index():
    if not session.get("user_id"): return redirect(url_for("login"))
    return redirect(url_for("superadmin" if session["role"] == "superadmin" else "admin"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=%s", (request.form.get("username","").strip(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password","")):
            session.clear()
            session.update(user_id=user["id"], username=user["username"], role=user["role"])
            return redirect(url_for("index"))
        flash("Login yoki parol noto‘g‘ri", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/superadmin")
@role_required("superadmin")
def superadmin():
    with db() as con:
        students = con.execute("SELECT COUNT(*) AS n FROM students").fetchone()["n"]
        records = con.execute("SELECT COUNT(*) AS n FROM attendance").fetchone()["n"]
        users = con.execute("SELECT id,username,role FROM users ORDER BY id").fetchall()
        recent = con.execute("""SELECT a.attendance_date,a.lesson,a.status,s.full_name,s.student_code
            FROM attendance a JOIN students s ON s.id=a.student_id
            ORDER BY a.id DESC LIMIT 12""").fetchall()
    return render_template("superadmin.html", students=students, records=records, users=users, recent=recent)

@app.route("/admin")
@role_required("superadmin","admin")
def admin():
    q = request.args.get("q","").strip()
    with db() as con:
        if q:
            students = con.execute("""SELECT * FROM students
                WHERE student_code ILIKE %s OR full_name ILIKE %s OR group_name ILIKE %s
                ORDER BY full_name LIMIT 300""", (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
        else:
            students = con.execute("SELECT * FROM students ORDER BY full_name LIMIT 300").fetchall()
        today_count = con.execute("SELECT COUNT(*) AS n FROM attendance WHERE attendance_date=%s", (date.today(),)).fetchone()["n"]
    return render_template("admin.html", students=students, today_count=today_count, q=q)

@app.route("/students/add", methods=["POST"])
@role_required("superadmin","admin")
def add_student():
    code=request.form.get("student_code","").strip()
    name=request.form.get("full_name","").strip()
    group=request.form.get("group_name","").strip()
    if not code or not name: flash("Student ID va F.I.Sh. majburiy","error")
    else:
        try:
            with db() as con:
                con.execute("INSERT INTO students(student_code,full_name,group_name) VALUES(%s,%s,%s)",(code,name,group))
            flash("Talaba qo‘shildi","success")
        except psycopg.errors.UniqueViolation: flash("Bu Student ID avval ro‘yxatdan o‘tgan","error")
    return redirect(url_for("admin"))

@app.route("/attendance/mark", methods=["POST"])
@role_required("superadmin","admin")
def mark_attendance():
    try:
        sid=int(request.form.get("student_id",""))
        day=date.fromisoformat(request.form.get("attendance_date") or date.today().isoformat())
    except (ValueError, TypeError):
        flash("Talaba yoki sana noto‘g‘ri","error"); return redirect(url_for("admin"))
    lesson=request.form.get("lesson","").strip()
    status=request.form.get("status","Present")
    if status not in ("Present","Absent","Late"): abort(400)
    with db() as con:
        result=con.execute("""INSERT INTO attendance(student_id,attendance_date,lesson,status,marked_by)
            VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(student_id,attendance_date,lesson) DO UPDATE SET
            status=EXCLUDED.status,marked_by=EXCLUDED.marked_by,created_at=NOW()
            RETURNING id""",(sid,day,lesson,status,session.get("username",""))).fetchone()
    if result: flash("Davomat saqlandi","success")
    else: flash("Talaba topilmadi","error")
    return redirect(url_for("admin"))

@app.route("/reports")
@role_required("superadmin","admin")
def reports():
    try: day=date.fromisoformat(request.args.get("date",date.today().isoformat()))
    except ValueError: day=date.today()
    with db() as con:
        rows=con.execute("""SELECT s.student_code,s.full_name,s.group_name,a.attendance_date,a.lesson,a.status,a.marked_by
            FROM attendance a JOIN students s ON s.id=a.student_id
            WHERE a.attendance_date=%s ORDER BY s.group_name,s.full_name""",(day,)).fetchall()
    return render_template("reports.html",rows=rows,day=day.isoformat())

@app.route("/export.csv")
@role_required("superadmin","admin")
def export_csv():
    try: day=date.fromisoformat(request.args.get("date",date.today().isoformat()))
    except ValueError: abort(400)
    with db() as con:
        rows=con.execute("""SELECT s.student_code,s.full_name,s.group_name,a.attendance_date,a.lesson,a.status,a.marked_by
            FROM attendance a JOIN students s ON s.id=a.student_id
            WHERE a.attendance_date=%s ORDER BY s.group_name,s.full_name""",(day,)).fetchall()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["Student ID","F.I.Sh.","Guruh","Sana","Dars","Holat","Belgilagan"])
    for r in rows: w.writerow([r[k] for k in ("student_code","full_name","group_name","attendance_date","lesson","status","marked_by")])
    data=io.BytesIO(("\ufeff"+out.getvalue()).encode("utf-8"))
    return send_file(data,mimetype="text/csv",as_attachment=True,download_name=f"davomat_{day}.csv")

@app.route("/users/add",methods=["POST"])
@role_required("superadmin")
def add_user():
    username=request.form.get("username","").strip()
    password=request.form.get("password","")
    role=request.form.get("role","admin")
    if not username or len(password)<8 or role not in ("admin","superadmin"):
        flash("Login kiriting, parol kamida 8 belgi bo‘lsin","error")
    else:
        try:
            with db() as con:
                con.execute("INSERT INTO users(username,password_hash,role) VALUES(%s,%s,%s)",(username,generate_password_hash(password),role))
            flash("Foydalanuvchi yaratildi","success")
        except psycopg.errors.UniqueViolation: flash("Bu login band","error")
    return redirect(url_for("superadmin"))

@app.route("/health")
def health(): return {"status":"ok"}

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
