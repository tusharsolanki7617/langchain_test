import os
import sqlite3
from pathlib import Path
import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Load environment variables
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SQLITE_PATH = Path(__file__).resolve().parent / "local_database.sqlite"

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "mcq_generator")


class Database:
    """Database helper supporting MySQL with automatic SQLite fallback."""

    def __init__(self):
        self.use_mysql = True
        self._test_connection()

    def _test_connection(self):
        try:
            conn = mysql.connector.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, database=DB_NAME, connect_timeout=3
            )
            conn.close()
            self.use_mysql = True
            print("Connected to MySQL successfully.")
        except Exception as e:
            print(f"Notice: MySQL unavailable ({e}). Operating in SQLite mode.")
            self.use_mysql = False

    def get_connection(self):
        if self.use_mysql:
            try:
                return mysql.connector.connect(
                    host=DB_HOST, port=DB_PORT, user=DB_USER,
                    password=DB_PASSWORD, database=DB_NAME
                )
            except Exception:
                self.use_mysql = False
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Schema ────────────────────────────────────────────────────────────

    def init_db(self, seed_demo_data=False):
        """Initialize tables. Optionally seed demo accounts if seed_demo_data=True."""
        conn = self.get_connection()
        cur  = conn.cursor()

        if self.use_mysql:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    first_name    VARCHAR(80)  NOT NULL,
                    last_name     VARCHAR(80)  NOT NULL,
                    email         VARCHAR(150) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role          ENUM('student','teacher','admin') NOT NULL,
                    -- student-specific
                    institute     VARCHAR(150),
                    roll_number   VARCHAR(50),
                    class_year    VARCHAR(80),
                    -- teacher-specific
                    department    VARCHAR(150),
                    -- account state
                    status        VARCHAR(20)  DEFAULT 'pending',
                    active        TINYINT(1)   DEFAULT 1,
                    reject_reason VARCHAR(255),
                    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                    last_login    TIMESTAMP    NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    user_id    INT,
                    user_email VARCHAR(150),
                    role       VARCHAR(50),
                    action     VARCHAR(100) NOT NULL,
                    details    VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name    TEXT NOT NULL,
                    last_name     TEXT NOT NULL,
                    email         TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role          TEXT NOT NULL,
                    institute     TEXT,
                    roll_number   TEXT,
                    class_year    TEXT,
                    department    TEXT,
                    status        TEXT DEFAULT 'pending',
                    active        INTEGER DEFAULT 1,
                    reject_reason TEXT,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login    TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER,
                    user_email TEXT,
                    role       TEXT,
                    action     TEXT NOT NULL,
                    details    TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()
        
        # Only seed demo data if explicitly requested
        if seed_demo_data:
            self._seed_defaults(conn)
        
        cur.close()
        conn.close()

    def _seed_defaults(self, conn):
        cur = conn.cursor()
        ph  = "%s" if self.use_mysql else "?"

        demo = [
            # first, last, email, pwd, role, institute, roll, class_year, dept, status
            ("Alex",   "Rivera",  "student@edux.com", "student123", "student",
             "Demo Institute of Technology", "CS2024001", "2nd Year · B.Tech CS", None, "approved"),
            ("Prof. Sarah", "Connor", "teacher@edux.com", "teacher123", "teacher",
             None, None, None, "Dept. of AI & Data Science", "approved"),
            ("System", "Admin",   "admin@edux.com",   "admin123",   "admin",
             None, None, None, None, "approved"),
        ]

        for first, last, email, pwd, role, inst, roll, cls, dept, status in demo:
            cur.execute(f"SELECT id FROM users WHERE email = {ph}", (email,))
            if cur.fetchone():
                continue
            pwd_hash = generate_password_hash(pwd)
            if self.use_mysql:
                cur.execute("""
                    INSERT INTO users
                      (first_name,last_name,email,password_hash,role,
                       institute,roll_number,class_year,department,status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (first, last, email, pwd_hash, role, inst, roll, cls, dept, status))
            else:
                cur.execute("""
                    INSERT INTO users
                      (first_name,last_name,email,password_hash,role,
                       institute,roll_number,class_year,department,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (first, last, email, pwd_hash, role, inst, roll, cls, dept, status))
        conn.commit()

    # ─── Finders ───────────────────────────────────────────────────────────

    def _row(self, row):
        if row is None:
            return None
        if not self.use_mysql:
            return dict(row)
        return row

    def find_user_by_email(self, email):
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"SELECT * FROM users WHERE email = {ph}", (email.strip().lower(),))
        row = self._row(cur.fetchone())
        cur.close(); conn.close()
        return row

    def find_user_by_id(self, user_id):
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"SELECT * FROM users WHERE id = {ph}", (user_id,))
        row = self._row(cur.fetchone())
        cur.close(); conn.close()
        return row

    # ─── Writers ───────────────────────────────────────────────────────────

    def create_user(self, first_name, last_name, email, password, role,
                    institute="", roll_number="", class_year="", department=""):
        conn     = self.get_connection()
        cur      = conn.cursor()
        pwd_hash = generate_password_hash(password)
        # Admins are auto-approved; students/teachers wait for approval
        status   = "approved" if role == "admin" else "pending"

        if self.use_mysql:
            cur.execute("""
                INSERT INTO users
                  (first_name,last_name,email,password_hash,role,
                   institute,roll_number,class_year,department,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (first_name.strip(), last_name.strip(), email.strip().lower(),
                  pwd_hash, role, institute.strip(), roll_number.strip(),
                  class_year.strip(), department.strip(), status))
        else:
            cur.execute("""
                INSERT INTO users
                  (first_name,last_name,email,password_hash,role,
                   institute,roll_number,class_year,department,status)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (first_name.strip(), last_name.strip(), email.strip().lower(),
                  pwd_hash, role, institute.strip(), roll_number.strip(),
                  class_year.strip(), department.strip(), status))

        user_id = cur.lastrowid
        conn.commit(); cur.close(); conn.close()
        return user_id, status

    def update_last_login(self, user_id):
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        sql  = f"UPDATE users SET last_login = {'NOW()' if self.use_mysql else 'CURRENT_TIMESTAMP'} WHERE id = {ph}"
        cur.execute(sql, (user_id,))
        conn.commit(); cur.close(); conn.close()

    def approve_user(self, user_id):
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"UPDATE users SET status='approved', reject_reason=NULL WHERE id={ph}", (user_id,))
        conn.commit(); cur.close(); conn.close()

    def reject_user(self, user_id, reason=""):
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"UPDATE users SET status='rejected', reject_reason={ph} WHERE id={ph}", (reason, user_id))
        conn.commit(); cur.close(); conn.close()

    def toggle_active(self, user_id):
        user = self.find_user_by_id(user_id)
        if not user:
            return None
        new_val = 0 if user.get("active") else 1
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"UPDATE users SET active={ph} WHERE id={ph}", (new_val, user_id))
        conn.commit(); cur.close(); conn.close()
        return new_val

    # ─── Admin Queries ─────────────────────────────────────────────────────

    def get_all_users(self, status_filter=None, role_filter=None, search=None):
        conn  = self.get_connection()
        cur   = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        where = ["role != 'admin'"]
        params = []
        ph = "%s" if self.use_mysql else "?"

        if status_filter and status_filter in ("pending","approved","rejected"):
            where.append(f"status = {ph}")
            params.append(status_filter)
        if role_filter and role_filter in ("student","teacher"):
            where.append(f"role = {ph}")
            params.append(role_filter)
        if search:
            s = f"%{search}%"
            where.append(f"(first_name LIKE {ph} OR last_name LIKE {ph} OR email LIKE {ph} OR roll_number LIKE {ph})")
            params += [s, s, s, s]

        sql = "SELECT * FROM users"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"

        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows and not self.use_mysql:
            return [dict(r) for r in rows]
        return rows

    def get_pending_users(self):
        return self.get_all_users(status_filter="pending")

    def get_role_counts(self):
        conn = self.get_connection()
        cur  = conn.cursor()
        counts = {"student": 0, "teacher": 0, "admin": 0,
                  "pending": 0, "approved": 0, "rejected": 0}
        cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
        for role, cnt in cur.fetchall():
            if role in counts:
                counts[role] = cnt
        cur.execute("SELECT status, COUNT(*) FROM users WHERE role != 'admin' GROUP BY status")
        for status, cnt in cur.fetchall():
            if status in counts:
                counts[status] = cnt
        cur.close(); conn.close()
        return counts

    def get_recent_logs(self, limit=15):
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT {ph}", (limit,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows and not self.use_mysql:
            return [dict(r) for r in rows]
        return rows

    def get_recent_signups(self, limit=8):
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"""
            SELECT id, first_name, last_name, email, role, status, created_at
            FROM users WHERE role != 'admin'
            ORDER BY created_at DESC LIMIT {ph}
        """, (limit,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows and not self.use_mysql:
            return [dict(r) for r in rows]
        return rows

    # ─── Audit Logging ─────────────────────────────────────────────────────

    def log_activity(self, user_id, user_email, role, action, details=""):
        try:
            conn = self.get_connection()
            cur  = conn.cursor()
            if self.use_mysql:
                cur.execute("""
                    INSERT INTO audit_logs (user_id,user_email,role,action,details)
                    VALUES (%s,%s,%s,%s,%s)
                """, (user_id, user_email, role, action, details))
            else:
                cur.execute("""
                    INSERT INTO audit_logs (user_id,user_email,role,action,details)
                    VALUES (?,?,?,?,?)
                """, (user_id, user_email, role, action, details))
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"Audit log error: {e}")


db = Database()
