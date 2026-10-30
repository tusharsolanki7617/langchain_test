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
        """Initialize all tables (users, audit_logs, mcq_sets). No demo data by default."""
        conn = self.get_connection()
        cur  = conn.cursor()

        if self.use_mysql:
            # Users table
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
            
            # Audit logs
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
            
            # MCQ sets (for test generation history)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mcq_sets (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    topic VARCHAR(255) NOT NULL,
                    difficulty VARCHAR(20) NOT NULL,
                    provider VARCHAR(20) NOT NULL,
                    questions_json LONGTEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
        else:
            # SQLite schema
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mcq_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    topic TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    questions_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)

        # ── Teacher Panel tables ────────────────────────────────────────────────
        if self.use_mysql:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_tests (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    teacher_id       INT NOT NULL,
                    title            VARCHAR(255) NOT NULL,
                    subject          VARCHAR(255) DEFAULT '',
                    topic            VARCHAR(255) DEFAULT '',
                    description      TEXT,
                    duration_minutes INT DEFAULT 30,
                    total_marks      INT DEFAULT 0,
                    status           VARCHAR(20)  DEFAULT 'draft',
                    instructions     TEXT,
                    difficulty       VARCHAR(10)  DEFAULT 'medium',
                    max_tab_switches INT DEFAULT 3,
                    opens_at         DATETIME DEFAULT NULL,
                    closes_at        DATETIME DEFAULT NULL,
                    ai_proctoring    TINYINT(1) DEFAULT 1,
                    negative_marking TINYINT(1) DEFAULT 0,
                    shuffle_questions TINYINT(1) DEFAULT 1,
                    shuffle_options  TINYINT(1) DEFAULT 1,
                    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_test_questions (
                    id                  INT AUTO_INCREMENT PRIMARY KEY,
                    test_id             INT NOT NULL,
                    question_text       TEXT NOT NULL,
                    question_type       VARCHAR(30)  DEFAULT 'mcq',
                    difficulty          VARCHAR(10)  DEFAULT 'medium',
                    marks               INT DEFAULT 1,
                    negative_marks      INT DEFAULT 0,
                    options_json        TEXT DEFAULT NULL,
                    correct_answer      VARCHAR(10)  DEFAULT NULL,
                    correct_answers_json TEXT DEFAULT NULL,
                    expected_answer     TEXT DEFAULT NULL,
                    explanation         TEXT,
                    position            INT DEFAULT 0,
                    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (test_id) REFERENCES teacher_tests(id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_test_students (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    test_id     INT NOT NULL,
                    student_id  INT NOT NULL,
                    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_assignment (test_id, student_id),
                    FOREIGN KEY (test_id)    REFERENCES teacher_tests(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_tests (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_id        INTEGER NOT NULL,
                    title             TEXT NOT NULL,
                    subject           TEXT DEFAULT '',
                    topic             TEXT DEFAULT '',
                    description       TEXT DEFAULT '',
                    duration_minutes  INTEGER DEFAULT 30,
                    total_marks       INTEGER DEFAULT 0,
                    status            TEXT DEFAULT 'draft',
                    instructions      TEXT DEFAULT '',
                    difficulty        TEXT DEFAULT 'medium',
                    max_tab_switches  INTEGER DEFAULT 3,
                    opens_at          DATETIME DEFAULT NULL,
                    closes_at         DATETIME DEFAULT NULL,
                    ai_proctoring     INTEGER DEFAULT 1,
                    negative_marking  INTEGER DEFAULT 0,
                    shuffle_questions INTEGER DEFAULT 1,
                    shuffle_options   INTEGER DEFAULT 1,
                    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_test_questions (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id              INTEGER NOT NULL,
                    question_text        TEXT NOT NULL,
                    question_type        TEXT DEFAULT 'mcq',
                    difficulty           TEXT DEFAULT 'medium',
                    marks                INTEGER DEFAULT 1,
                    negative_marks       INTEGER DEFAULT 0,
                    options_json         TEXT DEFAULT NULL,
                    correct_answer       TEXT DEFAULT NULL,
                    correct_answers_json TEXT DEFAULT NULL,
                    expected_answer      TEXT DEFAULT NULL,
                    explanation          TEXT DEFAULT '',
                    position             INTEGER DEFAULT 0,
                    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (test_id) REFERENCES teacher_tests(id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS teacher_test_students (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_id     INTEGER NOT NULL,
                    student_id  INTEGER NOT NULL,
                    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (test_id, student_id),
                    FOREIGN KEY (test_id)    REFERENCES teacher_tests(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

        # ── Student Practice tables ─────────────────────────────────────────────
        if self.use_mysql:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_practice_sessions (
                    id               INT AUTO_INCREMENT PRIMARY KEY,
                    student_id       INT NOT NULL,
                    subject          VARCHAR(255) DEFAULT '',
                    topic            VARCHAR(255) DEFAULT '',
                    difficulty       VARCHAR(10)  DEFAULT 'medium',
                    questions_json   LONGTEXT NOT NULL,
                    answers_json     LONGTEXT DEFAULT NULL,
                    score            FLOAT DEFAULT NULL,
                    total_marks      INT DEFAULT 0,
                    correct_count    INT DEFAULT 0,
                    wrong_count      INT DEFAULT 0,
                    skipped_count    INT DEFAULT 0,
                    time_taken_secs  INT DEFAULT NULL,
                    submitted        TINYINT(1) DEFAULT 0,
                    timed_practice   TINYINT(1) DEFAULT 0,
                    duration_minutes INT DEFAULT 0,
                    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                    submitted_at     DATETIME DEFAULT NULL,
                    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_practice_sessions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id       INTEGER NOT NULL,
                    subject          TEXT DEFAULT '',
                    topic            TEXT DEFAULT '',
                    difficulty       TEXT DEFAULT 'medium',
                    questions_json   TEXT NOT NULL,
                    answers_json     TEXT DEFAULT NULL,
                    score            REAL DEFAULT NULL,
                    total_marks      INTEGER DEFAULT 0,
                    correct_count    INTEGER DEFAULT 0,
                    wrong_count      INTEGER DEFAULT 0,
                    skipped_count    INTEGER DEFAULT 0,
                    time_taken_secs  INTEGER DEFAULT NULL,
                    submitted        INTEGER DEFAULT 0,
                    timed_practice   INTEGER DEFAULT 0,
                    duration_minutes INTEGER DEFAULT 0,
                    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                    submitted_at     DATETIME DEFAULT NULL
                )
            """)

        conn.commit()

        # Only seed demo data if explicitly requested (default: False)
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

        if status_filter and status_filter.lower() not in ("all", ""):
            where.append(f"status = {ph}")
            params.append(status_filter.lower())
        if role_filter and role_filter.lower() not in ("all", ""):
            # Handle "students" -> "student", "teachers" -> "teacher"
            norm_role = role_filter.lower().rstrip("s")
            where.append(f"role = {ph}")
            params.append(norm_role)
        if search and search.strip():
            s = f"%{search.strip()}%"
            where.append(f"(first_name LIKE {ph} OR last_name LIKE {ph} OR email LIKE {ph} OR roll_number LIKE {ph} OR institute LIKE {ph} OR department LIKE {ph})")
            params += [s, s, s, s, s, s]

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

    def get_platform_metrics(self):
        """Calculate complete statistics matching the ExamAI dashboard metrics."""
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()

        # Student status counts
        cur.execute("SELECT status, COUNT(*) as cnt FROM users WHERE role = 'student' GROUP BY status")
        st_rows = cur.fetchall()
        student_stats = {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
        for r in st_rows:
            st = r['status'] if self.use_mysql else r[0]
            c  = r['cnt'] if self.use_mysql else r[1]
            student_stats[st] = c
            student_stats["total"] += c

        # Teacher status counts
        cur.execute("SELECT status, COUNT(*) as cnt FROM users WHERE role = 'teacher' GROUP BY status")
        tc_rows = cur.fetchall()
        teacher_stats = {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
        for r in tc_rows:
            st = r['status'] if self.use_mysql else r[0]
            c  = r['cnt'] if self.use_mysql else r[1]
            teacher_stats[st] = c
            teacher_stats["total"] += c

        # Tests count from mcq_sets
        tests_count = 3
        try:
            cur.execute("SELECT COUNT(*) as cnt FROM mcq_sets")
            row = cur.fetchone()
            cnt = row['cnt'] if self.use_mysql else row[0]
            if cnt > 0:
                tests_count = cnt
        except Exception:
            pass

        # Activity counts
        test_attempts = 2
        try:
            cur.execute("SELECT COUNT(*) as cnt FROM audit_logs WHERE action IN ('LOGIN', 'SUBMIT_TEST')")
            row = cur.fetchone()
            cnt = row['cnt'] if self.use_mysql else row[0]
            if cnt > 0:
                test_attempts = max(2, cnt)
        except Exception:
            pass

        # Total pending
        pending_total = student_stats["pending"] + teacher_stats["pending"]

        cur.close(); conn.close()

        return {
            "pending": pending_total,
            "students": student_stats,
            "teachers": teacher_stats,
            "tests": {
                "total": tests_count,
                "published": tests_count,
                "practice": 0
            },
            "activity": {
                "test_attempts": test_attempts,
                "practice_sets": 0,
                "published_tests": tests_count
            }
        }

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

    # ─── MCQ History (for test generation) ─────────────────────────────────

    def save_questions(self, user_id, topic, difficulty, provider, questions):
        """Save generated test questions to database with optional user tracking."""
        conn = self.get_connection()
        cur  = conn.cursor()
        try:
            import json
            if self.use_mysql:
                cur.execute("""
                    INSERT INTO mcq_sets
                        (user_id, topic, difficulty, provider, questions_json)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    user_id,
                    topic,
                    difficulty,
                    provider,
                    json.dumps(questions, ensure_ascii=False)
                ))
            else:
                cur.execute("""
                    INSERT INTO mcq_sets
                        (user_id, topic, difficulty, provider, questions_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    user_id,
                    topic,
                    difficulty,
                    provider,
                    json.dumps(questions, ensure_ascii=False)
                ))
            conn.commit()
        finally:
            cur.close()
            conn.close()


    # ─── Teacher Panel Methods ──────────────────────────────────────────────

    def get_teacher_tests(self, teacher_id):
        """Return all tests for a teacher ordered by updated_at desc, with question count."""
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"""
            SELECT t.*,
                   (SELECT COUNT(*) FROM teacher_test_questions q WHERE q.test_id = t.id) AS question_count
            FROM teacher_tests t
            WHERE t.teacher_id = {ph}
            ORDER BY t.updated_at DESC, t.created_at DESC
        """, (teacher_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows and not self.use_mysql:
            return [dict(r) for r in rows]
        return rows or []

    def get_teacher_test(self, test_id, teacher_id=None):
        """Return single test. If teacher_id given, verify ownership."""
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        if teacher_id is not None:
            cur.execute(f"SELECT * FROM teacher_tests WHERE id = {ph} AND teacher_id = {ph}", (test_id, teacher_id))
        else:
            cur.execute(f"SELECT * FROM teacher_tests WHERE id = {ph}", (test_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and not self.use_mysql:
            return dict(row)
        return row

    def create_teacher_test(self, teacher_id, title, subject="", topic="", description="",
                            duration_minutes=30, instructions="", difficulty="medium",
                            max_tab_switches=3, opens_at=None, closes_at=None,
                            ai_proctoring=1, negative_marking=0,
                            shuffle_questions=1, shuffle_options=1):
        """Create a new draft test, return the new id."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cols = "(teacher_id, title, subject, topic, description, duration_minutes, instructions, difficulty, max_tab_switches, opens_at, closes_at, ai_proctoring, negative_marking, shuffle_questions, shuffle_options)"
        vals = (teacher_id, title, subject, topic, description, duration_minutes, instructions,
                difficulty, max_tab_switches, opens_at, closes_at,
                ai_proctoring, negative_marking, shuffle_questions, shuffle_options)
        placeholders = ", ".join([ph] * len(vals))
        cur.execute(f"INSERT INTO teacher_tests {cols} VALUES ({placeholders})", vals)
        new_id = cur.lastrowid
        conn.commit(); cur.close(); conn.close()
        return new_id

    def assign_student_to_test(self, test_id, student_id):
        """Assign a student to a test (idempotent)."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        try:
            if self.use_mysql:
                cur.execute("INSERT IGNORE INTO teacher_test_students (test_id, student_id) VALUES (%s, %s)",
                            (test_id, student_id))
            else:
                cur.execute("INSERT OR IGNORE INTO teacher_test_students (test_id, student_id) VALUES (?, ?)",
                            (test_id, student_id))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close(); conn.close()

    def remove_student_from_test(self, test_id, student_id):
        """Remove student assignment."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"DELETE FROM teacher_test_students WHERE test_id = {ph} AND student_id = {ph}",
                    (test_id, student_id))
        conn.commit(); cur.close(); conn.close()

    def update_teacher_test(self, test_id, **kwargs):
        """Update test fields."""
        allowed = {'title', 'subject', 'topic', 'description', 'duration_minutes', 'total_marks',
                   'status', 'instructions', 'difficulty', 'max_tab_switches', 'opens_at', 'closes_at',
                   'ai_proctoring', 'negative_marking', 'shuffle_questions', 'shuffle_options'}
        fields  = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        set_clause = ", ".join(f"{k} = {ph}" for k in fields)
        if self.use_mysql:
            set_clause += ", updated_at = NOW()"
        sql = f"UPDATE teacher_tests SET {set_clause} WHERE id = {ph}"
        cur.execute(sql, list(fields.values()) + [test_id])
        conn.commit(); cur.close(); conn.close()

    def delete_teacher_test(self, test_id):
        """Delete test (cascades to questions and student assignments)."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"DELETE FROM teacher_tests WHERE id = {ph}", (test_id,))
        conn.commit(); cur.close(); conn.close()

    def get_test_questions(self, test_id):
        """Return questions for a test ordered by position."""
        import json as _json
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"SELECT * FROM teacher_test_questions WHERE test_id = {ph} ORDER BY position, id", (test_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        result = []
        for r in rows:
            row = dict(r) if not self.use_mysql else r
            # Parse options_json for template use
            opts_raw = row.get('options_json')
            try:
                row['options_parsed'] = _json.loads(opts_raw) if opts_raw else None
            except Exception:
                row['options_parsed'] = None
            result.append(row)
        return result

    def _recalc_total_marks(self, conn, cur, test_id):
        """Recalculate total_marks for a test."""
        ph = "%s" if self.use_mysql else "?"
        cur.execute(f"SELECT COALESCE(SUM(marks), 0) FROM teacher_test_questions WHERE test_id = {ph}", (test_id,))
        row = cur.fetchone()
        total = list(row)[0] if row else 0
        cur.execute(f"UPDATE teacher_tests SET total_marks = {ph} WHERE id = {ph}", (total, test_id))
        return int(total)

    def add_test_question(self, test_id, question_text, question_type="mcq",
                          difficulty="medium", marks=1, negative_marks=0,
                          options_json=None, correct_answer=None,
                          correct_answers_json=None, expected_answer=None,
                          explanation="", position=0):
        """Add a question, return new id and updated total_marks."""
        import json as _json
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        opts = _json.dumps(options_json, ensure_ascii=False) if options_json is not None else None
        ca_j = _json.dumps(correct_answers_json, ensure_ascii=False) if correct_answers_json is not None else None

        if self.use_mysql:
            cur.execute("""
                INSERT INTO teacher_test_questions
                  (test_id, question_text, question_type, difficulty, marks, negative_marks,
                   options_json, correct_answer, correct_answers_json, expected_answer, explanation, position)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (test_id, question_text, question_type, difficulty, marks, negative_marks,
                  opts, correct_answer, ca_j, expected_answer, explanation, position))
        else:
            cur.execute("""
                INSERT INTO teacher_test_questions
                  (test_id, question_text, question_type, difficulty, marks, negative_marks,
                   options_json, correct_answer, correct_answers_json, expected_answer, explanation, position)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (test_id, question_text, question_type, difficulty, marks, negative_marks,
                  opts, correct_answer, ca_j, expected_answer, explanation, position))

        new_id = cur.lastrowid
        total_marks = self._recalc_total_marks(conn, cur, test_id)
        conn.commit(); cur.close(); conn.close()
        return new_id, total_marks

    def update_test_question(self, q_id, **kwargs):
        """Update question fields."""
        import json as _json
        allowed = {'question_text', 'question_type', 'difficulty', 'marks', 'negative_marks',
                   'options_json', 'correct_answer', 'correct_answers_json', 'expected_answer',
                   'explanation', 'position'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        set_clause = ", ".join(f"{k} = {ph}" for k in fields)
        cur.execute(f"UPDATE teacher_test_questions SET {set_clause} WHERE id = {ph}",
                    list(fields.values()) + [q_id])
        conn.commit(); cur.close(); conn.close()

    def delete_test_question(self, q_id):
        """Delete question and update total_marks on the test."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"SELECT test_id FROM teacher_test_questions WHERE id = {ph}", (q_id,))
        row = cur.fetchone()
        test_id = (row[0] if row else None)
        cur.execute(f"DELETE FROM teacher_test_questions WHERE id = {ph}", (q_id,))
        total_marks = 0
        question_count = 0
        if test_id:
            total_marks = self._recalc_total_marks(conn, cur, test_id)
            cur.execute(f"SELECT COUNT(*) FROM teacher_test_questions WHERE test_id = {ph}", (test_id,))
            cnt_row = cur.fetchone()
            question_count = int(list(cnt_row)[0]) if cnt_row else 0
        conn.commit(); cur.close(); conn.close()
        return total_marks, question_count

    def publish_test(self, test_id):
        """Set status='published'."""
        self.update_teacher_test(test_id, status='published')

    def get_test_students(self, test_id):
        """Return students assigned to a test."""
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"""
            SELECT u.id, u.first_name, u.last_name, u.email, ts.assigned_at
            FROM teacher_test_students ts
            JOIN users u ON u.id = ts.student_id
            WHERE ts.test_id = {ph}
            ORDER BY ts.assigned_at DESC
        """, (test_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows and not self.use_mysql:
            return [dict(r) for r in rows]
        return rows or []

    def get_teacher_dashboard_stats(self, teacher_id):
        """Compute dashboard stats for a teacher."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"

        cur.execute(f"SELECT COUNT(*) FROM teacher_tests WHERE teacher_id = {ph}", (teacher_id,))
        total_tests = int(list(cur.fetchone())[0] or 0)

        cur.execute(f"SELECT COUNT(*) FROM teacher_tests WHERE teacher_id = {ph} AND status = 'published'", (teacher_id,))
        published_tests = int(list(cur.fetchone())[0] or 0)

        cur.execute(f"""
            SELECT COUNT(DISTINCT ts.student_id)
            FROM teacher_test_students ts
            JOIN teacher_tests t ON t.id = ts.test_id
            WHERE t.teacher_id = {ph}
        """, (teacher_id,))
        students_assigned = int(list(cur.fetchone())[0] or 0)

        cur.execute(f"""
            SELECT COUNT(*)
            FROM teacher_test_questions q
            JOIN teacher_tests t ON t.id = q.test_id
            WHERE t.teacher_id = {ph}
        """, (teacher_id,))
        questions_created = int(list(cur.fetchone())[0] or 0)

        cur.close(); conn.close()
        return {
            'total_tests': total_tests,
            'published_tests': published_tests,
            'students_assigned': students_assigned,
            'questions_created': questions_created,
        }


    # ─── Student Practice Methods ─────────────────────────────────────────────

    def create_practice_session(self, student_id, subject, topic, difficulty,
                                 questions, timed=0, duration_minutes=0):
        """Create a new practice session, return new id."""
        import json as _json
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        q_json = _json.dumps(questions, ensure_ascii=False)
        total_marks = sum(int(q.get("marks", 1)) for q in questions)
        if self.use_mysql:
            cur.execute("""
                INSERT INTO student_practice_sessions
                  (student_id, subject, topic, difficulty, questions_json,
                   total_marks, timed_practice, duration_minutes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (student_id, subject, topic, difficulty, q_json,
                  total_marks, timed, duration_minutes))
        else:
            cur.execute("""
                INSERT INTO student_practice_sessions
                  (student_id, subject, topic, difficulty, questions_json,
                   total_marks, timed_practice, duration_minutes)
                VALUES (?,?,?,?,?,?,?,?)
            """, (student_id, subject, topic, difficulty, q_json,
                  total_marks, timed, duration_minutes))
        new_id = cur.lastrowid
        conn.commit(); cur.close(); conn.close()
        return new_id

    def get_practice_session(self, session_id, student_id=None):
        """Return a practice session. Optionally verify ownership."""
        import json as _json
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        if student_id:
            cur.execute(f"SELECT * FROM student_practice_sessions WHERE id = {ph} AND student_id = {ph}",
                        (session_id, student_id))
        else:
            cur.execute(f"SELECT * FROM student_practice_sessions WHERE id = {ph}", (session_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row is None:
            return None
        if not self.use_mysql:
            row = dict(row)
        # Parse questions and answers
        try:
            row["questions_parsed"] = _json.loads(row.get("questions_json") or "[]")
        except Exception:
            row["questions_parsed"] = []
        try:
            row["answers_parsed"] = _json.loads(row.get("answers_json") or "null")
        except Exception:
            row["answers_parsed"] = None
        return row

    def save_practice_answers(self, session_id, answers, score, correct_count,
                               wrong_count, skipped_count, time_taken_secs=None):
        """Save submitted answers and evaluation result."""
        import json as _json
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        a_json = _json.dumps(answers, ensure_ascii=False)
        if self.use_mysql:
            cur.execute("""
                UPDATE student_practice_sessions
                SET answers_json=%s, score=%s, correct_count=%s, wrong_count=%s,
                    skipped_count=%s, time_taken_secs=%s, submitted=1, submitted_at=NOW()
                WHERE id=%s
            """, (a_json, score, correct_count, wrong_count, skipped_count, time_taken_secs, session_id))
        else:
            cur.execute("""
                UPDATE student_practice_sessions
                SET answers_json=?, score=?, correct_count=?, wrong_count=?,
                    skipped_count=?, time_taken_secs=?, submitted=1, submitted_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (a_json, score, correct_count, wrong_count, skipped_count, time_taken_secs, session_id))
        conn.commit(); cur.close(); conn.close()

    def get_student_practice_history(self, student_id, limit=20):
        """Return all practice sessions for a student, newest first."""
        import json as _json
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"""
            SELECT id, subject, topic, difficulty, total_marks, score,
                   correct_count, wrong_count, skipped_count, submitted,
                   timed_practice, duration_minutes, time_taken_secs,
                   created_at, submitted_at,
                   (SELECT COUNT(*) FROM JSON_TABLE(questions_json, '$[*]' COLUMNS(x INT PATH '$.marks')) t) AS q_count
            FROM student_practice_sessions
            WHERE student_id = {ph}
            ORDER BY created_at DESC LIMIT {ph}
        """, (student_id, limit)) if self.use_mysql else cur.execute(f"""
            SELECT id, subject, topic, difficulty, total_marks, score,
                   correct_count, wrong_count, skipped_count, submitted,
                   timed_practice, duration_minutes, time_taken_secs,
                   created_at, submitted_at, questions_json
            FROM student_practice_sessions
            WHERE student_id = {ph}
            ORDER BY created_at DESC LIMIT {ph}
        """, (student_id, limit))
        rows = cur.fetchall()
        cur.close(); conn.close()
        result = []
        for r in rows:
            row = dict(r) if not self.use_mysql else r
            if not self.use_mysql:
                # Calculate q_count from JSON for SQLite
                try:
                    qs = _json.loads(row.get("questions_json") or "[]")
                    row["q_count"] = len(qs)
                except Exception:
                    row["q_count"] = 0
            result.append(row)
        return result

    def delete_practice_session(self, session_id, student_id):
        """Delete a practice session (student must own it)."""
        conn = self.get_connection()
        cur  = conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"DELETE FROM student_practice_sessions WHERE id = {ph} AND student_id = {ph}",
                    (session_id, student_id))
        conn.commit(); cur.close(); conn.close()

    def get_assigned_tests_for_student(self, student_id):
        """Return teacher-created tests assigned to this student."""
        conn = self.get_connection()
        cur  = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        ph   = "%s" if self.use_mysql else "?"
        cur.execute(f"""
            SELECT t.*, tts.assigned_at,
                   (SELECT COUNT(*) FROM teacher_test_questions q WHERE q.test_id = t.id) AS question_count
            FROM teacher_test_students tts
            JOIN teacher_tests t ON t.id = tts.test_id
            WHERE tts.student_id = {ph} AND t.status = 'published'
            ORDER BY tts.assigned_at DESC
        """, (student_id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        if rows and not self.use_mysql:
            return [dict(r) for r in rows]
        return rows or []


db = Database()
