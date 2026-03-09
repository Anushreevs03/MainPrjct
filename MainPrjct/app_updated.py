import sqlite3
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import random
import string
from datetime import datetime, timedelta
import time

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# SQLite Connection - for production, use PostgreSQL/MySQL with proper connection pooling
# For SQLite, we keep check_same_thread=False for development; remove for production
conn = sqlite3.connect("classroom.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Create Tables (PostgreSQL/MySQL compatible)
cursor.execute("""
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    class_code TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT NOT NULL,
    class_id INTEGER,
    violations INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id)
)
""")

# Activity events table - stores all student activity for historical tracking
cursor.execute("""
CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (class_id) REFERENCES classes(id)
)
""")

# Student sessions table - tracks active sessions
cursor.execute("""
CREATE TABLE IF NOT EXISTS student_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (class_id) REFERENCES classes(id)
)
""")

conn.commit()


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ---------------- CREATE CLASS ----------------
@app.route('/create_class', methods=['POST'])
def create_class():
    try:
        data = request.get_json()

        if not data or "class_name" not in data:
            return jsonify({"error": "Class name required"}), 400

        class_name = data["class_name"]

        # Ensure unique class code
        while True:
            class_code = generate_code()
            cursor.execute("SELECT id FROM classes WHERE class_code=?", (class_code,))
            if not cursor.fetchone():
                break

        cursor.execute(
            "INSERT INTO classes (class_name, class_code) VALUES (?, ?)",
            (class_name, class_code)
        )
        conn.commit()

        return jsonify({
            "success": True,
            "class_code": class_code
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- JOIN CLASS ----------------
@app.route('/join_class', methods=['POST'])
def join_class():
    try:
        data = request.get_json()

        if not data or "student_name" not in data or "class_code" not in data:
            return jsonify({"error": "Student name and class code required"}), 400

        student_name = data["student_name"]
        class_code = data["class_code"]

        cursor.execute("SELECT id FROM classes WHERE class_code=?", (class_code,))
        classroom = cursor.fetchone()

        if not classroom:
            return jsonify({"error": "Invalid class code"}), 400

        cursor.execute(
            "INSERT INTO students (student_name, class_id) VALUES (?, ?)",
            (student_name, classroom[0])
        )
        conn.commit()

        # Get the inserted student ID
        student_id = cursor.lastrowid

        # Create a new session for the student
        cursor.execute(
            "INSERT INTO student_sessions (student_id, class_id) VALUES (?, ?)",
            (student_id, classroom[0])
        )
        conn.commit()

        return jsonify({
            "success": True,
            "message": "Joined successfully",
            "student_id": student_id,
            "class_id": classroom[0]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template("index.html")


# ---------------- STUDENT ACTIVITY TRACKING ----------------

# Record student activity event
@app.route('/student_activity', methods=['POST'])
def record_activity():
    try:
        data = request.get_json()

        if not data or "student_id" not in data or "class_id" not in data or "event_type" not in data:
            return jsonify({"error": "student_id, class_id, and event_type required"}), 400

        student_id = data["student_id"]
        class_id = data["class_id"]
        event_type = data["event_type"]
        event_details = data.get("event_details", "")

        # Validate event_type
        valid_event_types = [
            "app_switch", "tab_switch", "window_blur", "back_button", 
            "idle", "leave_app", "page_refresh", "tab_close", 
            "window_close", "focus"
        ]

        if event_type not in valid_event_types:
            return jsonify({"error": "Invalid event_type"}), 400

        # Insert activity event
        cursor.execute(
            "INSERT INTO activity_events (student_id, class_id, event_type, event_details) VALUES (?, ?, ?, ?)",
            (student_id, class_id, event_type, event_details)
        )
        conn.commit()

        # Update student violations count for concerning events
        concerning_events = ["app_switch", "tab_switch", "window_blur", "back_button", "idle", "leave_app", "tab_close", "window_close"]
        if event_type in concerning_events:
            cursor.execute(
                "UPDATE students SET violations = violations + 1 WHERE id = ?",
                (student_id,)
            )
            conn.commit()

        return jsonify({
            "success": True,
            "event_id": cursor.lastrowid
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Get class activities (historical tracking)
@app.route('/class_activities/<class_code>', methods=['GET'])
def get_class_activities(class_code):
    try:
        cursor.execute("SELECT id FROM classes WHERE class_code = ?", (class_code,))
        class_row = cursor.fetchone()

        if not class_row:
            return jsonify({"error": "Class not found"}), 404

        class_id = class_row[0]

        cursor.execute("""
            SELECT ae.id, ae.event_type, ae.event_details, ae.timestamp, 
                   s.student_name, s.violations
            FROM activity_events ae
            JOIN students s ON ae.student_id = s.id
            WHERE ae.class_id = ?
            ORDER BY ae.timestamp DESC
            LIMIT 100
        """, (class_id,))

        activities = cursor.fetchall()

        result = []
        for activity in activities:
            result.append({
                "id": activity[0],
                "event_type": activity[1],
                "event_details": activity[2],
                "timestamp": activity[3],
                "student_name": activity[4],
                "violations": activity[5]
            })

        return jsonify({
            "success": True,
            "activities": result
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Teacher notifications - poll for new alerts
@app.route('/teacher_notifications/<class_id>', methods=['GET'])
def get_teacher_notifications(class_id):
    try:
        last_timestamp = request.headers.get('Last-Timestamp', '0')

        cursor.execute("""
            SELECT ae.id, ae.event_type, ae.event_details, ae.timestamp,
                   s.student_name, s.id as student_id
            FROM activity_events ae
            JOIN students s ON ae.student_id = s.id
            WHERE ae.class_id = ? AND ae.timestamp > ?
            ORDER BY ae.timestamp DESC
            LIMIT 50
        """, (class_id, last_timestamp))

        notifications = cursor.fetchall()

        result = []
        for notif in notifications:
            result.append({
                "id": notif[0],
                "event_type": notif[1],
                "event_details": notif[2],
                "timestamp": notif[3],
                "student_name": notif[4],
                "student_id": notif[5]
            })

        cursor.execute("""
            SELECT s.id, s.student_name, s.violations, s.created_at, ss.session_start
            FROM students s
            JOIN student_sessions ss ON s.id = ss.student_id
            WHERE s.class_id = ? AND ss.is_active = 1
            ORDER BY ss.session_start ASC
        """, (class_id,))

        students = cursor.fetchall()
        active_students = []
        for student in students:
            active_students.append({
                "id": student[0],
                "student_name": student[1],
                "violations": student[2],
                "joined_at": student[3],
                "session_start": student[4]
            })

        return jsonify({
            "success": True,
            "notifications": result,
            "active_students": active_students
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Student leaves class (end session)
@app.route('/leave_class', methods=['POST'])
def leave_class():
    try:
        data = request.get_json()

        if not data or "student_id" not in data or "class_id" not in data:
            return jsonify({"error": "student_id and class_id required"}), 400

        student_id = data["student_id"]
        class_id = data["class_id"]

        cursor.execute("""
            UPDATE student_sessions 
            SET is_active = 0, session_end = CURRENT_TIMESTAMP 
            WHERE student_id = ? AND class_id = ? AND is_active = 1
        """, (student_id, class_id))
        conn.commit()

        return jsonify({
            "success": True,
            "message": "Left class successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Get class by class code
@app.route('/get_class/<class_code>', methods=['GET'])
def get_class(class_code):
    try:
        cursor.execute("SELECT id, class_name, class_code FROM classes WHERE class_code = ?", (class_code,))
        class_row = cursor.fetchone()

        if not class_row:
            return jsonify({"error": "Class not found"}), 404

        return jsonify({
            "success": True,
            "class": {
                "id": class_row[0],
                "class_name": class_row[1],
                "class_code": class_row[2]
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== STUDENT MONITORING DASHBOARD API ====================

# Get active students with detailed info for dashboard
@app.route('/api/dashboard/<class_id>', methods=['GET'])
def get_dashboard_students(class_id):
    try:
        # Get active students with their session info
        cursor.execute("""
            SELECT 
                s.id as student_id,
                s.student_name,
                s.violations,
                ss.session_start,
                (SELECT event_type FROM activity_events 
                 WHERE student_id = s.id AND class_id = s.class_id 
                 ORDER BY timestamp DESC LIMIT 1) as last_activity,
                (SELECT event_details FROM activity_events 
                 WHERE student_id = s.id AND class_id = s.class_id 
                 ORDER BY timestamp DESC LIMIT 1) as last_app
            FROM students s
            JOIN student_sessions ss ON s.id = ss.student_id
            WHERE s.class_id = ? AND ss.is_active = 1
            ORDER BY ss.session_start DESC
        """, (class_id,))

        students = cursor.fetchall()
        
        now = datetime.now()
        result = []
        
        for student in students:
            # Calculate session duration
            session_start = datetime.strptime(student[3], '%Y-%m-%d %H:%M:%S') if isinstance(student[3], str) else student[3]
            duration = now - session_start
            total_minutes = int(duration.total_seconds() / 60)
            
            # Get app name from last activity or default
            current_app = student[5] if student[5] else "Chrome"
            if not current_app or current_app == "":
                current_app = "Chrome"
            
            result.append({
                "student_id": student[0],
                "student_name": student[1],
                "violations": student[2],
                "session_start": student[3],
                "joined_time": student[3],
                "total_usage_minutes": total_minutes,
                "current_app": current_app,
                "is_active": True,
                "has_violation": student[2] > 0
            })

        return jsonify({
            "success": True,
            "students": result_active": len(result,
            "total),
            "timestamp": now.isoformat()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Update student current app (reported by client)
@app.route('/api/student/app', methods=['POST'])
def update_student_app():
    try:
        data = request.get_json()
        
        if not data or "student_id" not in data or "app_name" not in data:
            return jsonify({"error": "student_id and app_name required"}), 400
        
        student_id = data["student_id"]
        app_name = data["app_name"]
        
        # Record the app usage as an activity
        cursor.execute(
            "INSERT INTO activity_events (student_id, class_id, event_type, event_details) VALUES (?, (SELECT class_id FROM students WHERE id = ?), 'app_usage', ?)",
            (student_id, student_id, app_name)
        )
        conn.commit()
        
        # Emit WebSocket event for real-time update
        socketio.emit('app_update', {
            'student_id': student_id,
            'app_name': app_name
        })
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Get all available classes
@app.route('/api/classes', methods=['GET'])
def get_all_classes():
    try:
        cursor.execute("""
            SELECT c.id, c.class_name, c.class_code, c.created_at,
                   (SELECT COUNT(*) FROM student_sessions ss 
                    JOIN students s ON ss.student_id = s.id 
                    WHERE s.class_id = c.id AND ss.is_active = 1) as active_students
            FROM classes c
            ORDER BY c.created_at DESC
        """)
        
        classes = cursor.fetchall()
        result = []
        for cls in classes:
            result.append({
                "id": cls[0],
                "class_name": cls[1],
                "class_code": cls[2],
                "created_at": cls[3],
                "active_students": cls[4]
            })
        
        return jsonify({
            "success": True,
            "classes": result
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== WEBSOCKET HANDLERS ====================

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@socketio.on('join_classroom')
def handle_join_classroom(data):
    class_id = data.get('class_id')
    if class_id:
        emit('room_joined', {'class_id': class_id}, broadcast=True)


@socketio.on('student_joined')
def handle_student_joined(data):
    """Broadcast when a student joins"""
    socketio.emit('student_joined', data, broadcast=True)


@socketio.on('student_left')
def handle_student_left(data):
    """Broadcast when a student leaves"""
    socketio.emit('student_left', data, broadcast=True)


@socketio.on('violation_detected')
def handle_violation(data):
    """Broadcast when a violation is detected"""
    socketio.emit('violation', data, broadcast=True)


@socketio.on('app_changed')
def handle_app_changed(data):
    """Broadcast when a student changes app"""
    socketio.emit('app_update', data, broadcast=True)


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5050, allow_unsafe_werkzeug=True)
