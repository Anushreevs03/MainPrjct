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

# SQLite Connection
conn = sqlite3.connect("classroom.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Create Tables
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


@app.route('/create_class', methods=['POST'])
def create_class():
    try:
        data = request.get_json()
        if not data or "class_name" not in data:
            return jsonify({"error": "Class name required"}), 400
        class_name = data["class_name"]
        while True:
            class_code = generate_code()
            cursor.execute("SELECT id FROM classes WHERE class_code=?", (class_code,))
            if not cursor.fetchone():
                break
        cursor.execute("INSERT INTO classes (class_name, class_code) VALUES (?, ?)", (class_name, class_code))
        conn.commit()
        return jsonify({"success": True, "class_code": class_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        cursor.execute("INSERT INTO students (student_name, class_id) VALUES (?, ?)", (student_name, classroom[0]))
        conn.commit()
        student_id = cursor.lastrowid
        cursor.execute("INSERT INTO student_sessions (student_id, class_id) VALUES (?, ?)", (student_id, classroom[0]))
        conn.commit()
        return jsonify({"success": True, "message": "Joined successfully", "student_id": student_id, "class_id": classroom[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/')
def home():
    return render_template("index.html")


@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")


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
        valid_event_types = ["app_switch", "tab_switch", "window_blur", "back_button", "idle", "leave_app", "page_refresh", "tab_close", "window_close", "focus"]
        if event_type not in valid_event_types:
            return jsonify({"error": "Invalid event_type"}), 400
        cursor.execute("INSERT INTO activity_events (student_id, class_id, event_type, event_details) VALUES (?, ?, ?, ?)", (student_id, class_id, event_type, event_details))
        conn.commit()
        concerning_events = ["app_switch", "tab_switch", "window_blur", "back_button", "idle", "leave_app", "tab_close", "window_close"]
        if event_type in concerning_events:
            cursor.execute("UPDATE students SET violations = violations + 1 WHERE id = ?", (student_id,))
            conn.commit()
        return jsonify({"success": True, "event_id": cursor.lastrowid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/class_activities/<class_code>', methods=['GET'])
def get_class_activities(class_code):
    try:
        cursor.execute("SELECT id FROM classes WHERE class_code = ?", (class_code,))
        class_row = cursor.fetchone()
        if not class_row:
            return jsonify({"error": "Class not found"}), 404
        class_id = class_row[0]
        cursor.execute("""
            SELECT ae.id, ae.event_type, ae.event_details, ae.timestamp, s.student_name, s.violations
            FROM activity_events ae
            JOIN students s ON ae.student_id = s.id
            WHERE ae.class_id = ?
            ORDER BY ae.timestamp DESC
            LIMIT 100
        """, (class_id,))
        activities = cursor.fetchall()
        result = []
        for activity in activities:
            result.append({"id": activity[0], "event_type": activity[1], "event_details": activity[2], "timestamp": activity[3], "student_name": activity[4], "violations": activity[5]})
        return jsonify({"success": True, "activities": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/teacher_notifications/<class_id>', methods=['GET'])
def get_teacher_notifications(class_id):
    try:
        last_timestamp = request.headers.get('Last-Timestamp', '0')
        cursor.execute("""
            SELECT ae.id, ae.event_type, ae.event_details, ae.timestamp, s.student_name, s.id as student_id
            FROM activity_events ae
            JOIN students s ON ae.student_id = s.id
            WHERE ae.class_id = ? AND ae.timestamp > ?
            ORDER BY ae.timestamp DESC
            LIMIT 50
        """, (class_id, last_timestamp))
        notifications = cursor.fetchall()
        result = []
        for notif in notifications:
            result.append({"id": notif[0], "event_type": notif[1], "event_details": notif[2], "timestamp": notif[3], "student_name": notif[4], "student_id": notif[5]})
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
            active_students.append({"id": student[0], "student_name": student[1], "violations": student[2], "joined_at": student[3], "session_start": student[4]})
        return jsonify({"success": True, "notifications": result, "active_students": active_students})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/leave_class', methods=['POST'])
def leave_class():
    try:
        data = request.get_json()
        if not data or "student_id" not in data or "class_id" not in data:
            return jsonify({"error": "student_id and class_id required"}), 400
        student_id = data["student_id"]
        class_id = data["class_id"]
        cursor.execute("UPDATE student_sessions SET is_active = 0, session_end = CURRENT_TIMESTAMP WHERE student_id = ? AND class_id = ? AND is_active = 1", (student_id, class_id))
        conn.commit()
        return jsonify({"success": True, "message": "Left class successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/get_class/<class_code>', methods=['GET'])
def get_class(class_code):
    try:
        cursor.execute("SELECT id, class_name, class_code FROM classes WHERE class_code = ?", (class_code,))
        class_row = cursor.fetchone()
        if not class_row:
            return jsonify({"error": "Class not found"}), 404
        return jsonify({"success": True, "class": {"id": class_row[0], "class_name": class_row[1], "class_code": class_row[2]}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== STUDENT MONITORING DASHBOARD API ====================

@app.route('/api/dashboard/<class_id>', methods=['GET'])
def get_dashboard_students(class_id):
    try:
        cursor.execute("""
            SELECT s.id as student_id, s.student_name, s.violations, ss.session_start,
                   (SELECT event_details FROM activity_events WHERE student_id = s.id AND class_id = s.class_id ORDER BY timestamp DESC LIMIT 1) as last_app
            FROM students s
            JOIN student_sessions ss ON s.id = ss.student_id
            WHERE s.class_id = ? AND ss.is_active = 1
            ORDER BY ss.session_start DESC
        """, (class_id,))
        students = cursor.fetchall()
        now = datetime.now()
        result = []
        for student in students:
            session_start = datetime.strptime(student[3], '%Y-%m-%d %H:%M:%S') if isinstance(student[3], str) else student[3]
            duration = now - session_start
            total_minutes = int(duration.total_seconds() / 60)
            current_app = student[4] if student[4] else "Chrome"
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
        return jsonify({"success": True, "students": result, "total_active": len(result), "timestamp": now.isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/student/app', methods=['POST'])
def update_student_app():
    try:
        data = request.get_json()
        if not data or "student_id" not in data or "app_name" not in data:
            return jsonify({"error": "student_id and app_name required"}), 400
        student_id = data["student_id"]
        app_name = data["app_name"]
        cursor.execute("INSERT INTO activity_events (student_id, class_id, event_type, event_details) VALUES (?, (SELECT class_id FROM students WHERE id = ?), 'app_usage', ?)", (student_id, student_id, app_name))
        conn.commit()
        socketio.emit('app_update', {'student_id': student_id, 'app_name': app_name})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/classes', methods=['GET'])
def get_all_classes():
    try:
        cursor.execute("""
            SELECT c.id, c.class_name, c.class_code, c.created_at,
                   (SELECT COUNT(*) FROM student_sessions ss JOIN students s ON ss.student_id = s.id WHERE s.class_id = c.id AND ss.is_active = 1) as active_students
            FROM classes c ORDER BY c.created_at DESC
        """)
        classes = cursor.fetchall()
        result = []
        for cls in classes:
            result.append({"id": cls[0], "class_name": cls[1], "class_code": cls[2], "created_at": cls[3], "active_students": cls[4]})
        return jsonify({"success": True, "classes": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== WEBSOCKET HANDLERS ====================

# Store active student sessions in memory for real-time tracking
active_students = {}  # {student_id: {student_name, class_id, join_timestamp, active_app, session_id}}

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')
    # Note: Individual student removal is handled by student_left event
    # This is a fallback to clean up any stale connections

@socketio.on('join_classroom')
def handle_join_classroom(data):
    class_id = data.get('class_id')
    if class_id:
        emit('room_joined', {'class_id': class_id}, broadcast=True)

@socketio.on('student_joined')
def handle_student_joined(data):
    # Store student in active sessions
    student_id = data.get('student_id')
    student_name = data.get('student_name')
    class_id = data.get('class_id')
    join_timestamp = data.get('join_timestamp')
    active_app = data.get('active_app', 'Unknown')
    
    if student_id:
        active_students[student_id] = {
            'student_name': student_name,
            'class_id': class_id,
            'join_timestamp': join_timestamp,
            'active_app': active_app
        }
        
    socketio.emit('student_joined', data, broadcast=True)

@socketio.on('student_left')
def handle_student_left(data):
    student_id = data.get('student_id')
    if student_id and student_id in active_students:
        student_name = active_students[student_id]['student_name']
        del active_students[student_id]
        
        socketio.emit('student_left', {
            'student_id': student_id,
            'student_name': student_name
        }, broadcast=True)

@socketio.on('violation_detected')
def handle_violation(data):
    socketio.emit('violation', data, broadcast=True)

@socketio.on('app_changed')
def handle_app_changed(data):
    student_id = data.get('student_id')
    app_name = data.get('app_name')
    
    # Update active app in memory
    if student_id and student_id in active_students:
        active_students[student_id]['active_app'] = app_name
    
    socketio.emit('app_update', data, broadcast=True)

@socketio.on('update_student_app')
def handle_update_student_app(data):
    """Handle real-time app usage updates from student client"""
    student_id = data.get('student_id')
    app_name = data.get('app_name')
    duration = data.get('duration', 0)
    
    if student_id and student_id in active_students:
        active_students[student_id]['active_app'] = app_name
        active_students[student_id]['app_usage_duration'] = duration
    
    # Emit to all connected clients
    socketio.emit('student_app_update', {
        'student_id': student_id,
        'student_name': active_students.get(student_id, {}).get('student_name', 'Unknown'),
        'active_app': app_name,
        'duration': duration,
        'timestamp': datetime.now().isoformat()
    }, broadcast=True)

@socketio.on('student_activity')
def handle_student_activity(data):
    """Handle real-time activity/violation events"""
    student_id = data.get('student_id')
    event_type = data.get('event_type')
    event_details = data.get('event_details', '')
    
    # Get student info
    student_name = 'Unknown'
    if student_id and student_id in active_students:
        student_name = active_students[student_id].get('student_name', 'Unknown')
    
    # Emit violation event to all clients
    socketio.emit('violation_event', {
        'student_id': student_id,
        'student_name': student_name,
        'event_type': event_type,
        'event_details': event_details,
        'timestamp': datetime.now().isoformat()
    }, broadcast=True)

# ==================== NEW REAL-TIME API ENDPOINTS ====================

@app.route('/api/real-time/students/<class_id>', methods=['GET'])
def get_real_time_students(class_id):
    """Get all active students with real-time data, sorted by join time (most recent first)"""
    try:
        cursor.execute("""
            SELECT s.id as student_id, s.student_name, s.violations, ss.session_start,
                   (SELECT event_details FROM activity_events 
                    WHERE student_id = s.id AND class_id = s.class_id 
                    ORDER BY timestamp DESC LIMIT 1) as last_app,
                   (SELECT COUNT(*) FROM activity_events 
                    WHERE student_id = s.id AND event_type IN ('app_switch', 'tab_switch', 'window_blur', 'back_button', 'idle', 'leave_app', 'tab_close', 'window_close')) as violation_count
            FROM students s
            JOIN student_sessions ss ON s.id = ss.student_id
            WHERE s.class_id = ? AND ss.is_active = 1
            ORDER BY ss.session_start DESC
        """, (class_id,))
        
        students = cursor.fetchall()
        now = datetime.now()
        result = []
        
        for student in students:
            session_start = datetime.strptime(student[3], '%Y-%m-%d %H:%M:%S') if isinstance(student[3], str) else student[3]
            duration = now - session_start
            total_minutes = int(duration.total_seconds() / 60)
            current_app = student[4] if student[4] else "Chrome"
            
            if not current_app or current_app == "":
                current_app = "Chrome"
            
            # Get recent violation events
            cursor.execute("""
                SELECT event_type, event_details, timestamp 
                FROM activity_events 
                WHERE student_id = ? AND class_id = ? AND event_type IN ('app_switch', 'tab_switch', 'window_blur', 'back_button', 'idle', 'leave_app', 'tab_close', 'window_close')
                ORDER BY timestamp DESC LIMIT 10
            """, (student[0], class_id))
            
            violations = cursor.fetchall()
            violation_events = []
            for v in violations:
                violation_events.append({
                    'event_type': v[0],
                    'event_details': v[1],
                    'timestamp': v[2]
                })
            
            result.append({
                'student_id': student[0],
                'student_name': student[1],
                'violations': student[2],
                'join_timestamp': student[3].isoformat() if hasattr(student[3], 'isoformat') else student[3],
                'active_app': current_app,
                'app_usage_duration': total_minutes,
                'violation_events': violation_events,
                'has_violation': student[2] > 0
            })
        
        # Sort by most recent join time (already sorted by SQL, but ensure)
        result.sort(key=lambda x: x['join_timestamp'], reverse=True)
        
        return jsonify({
            "success": True, 
            "students": result, 
            "total_active": len(result),
            "timestamp": now.isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/student/session', methods=['POST'])
def create_student_session():
    """Create a new student session with join timestamp"""
    try:
        data = request.get_json()
        if not data or "student_id" not in data or "class_id" not in data:
            return jsonify({"error": "student_id and class_id required"}), 400
        
        student_id = data["student_id"]
        class_id = data["class_id"]
        
        # Get student name
        cursor.execute("SELECT student_name FROM students WHERE id = ?", (student_id,))
        student = cursor.fetchone()
        if not student:
            return jsonify({"error": "Student not found"}), 404
        
        student_name = student[0]
        join_timestamp = datetime.now().isoformat()
        
        # Create session
        cursor.execute("""
            INSERT INTO student_sessions (student_id, class_id, is_active) 
            VALUES (?, ?, 1)
        """, (student_id, class_id))
        conn.commit()
        
        session_id = cursor.lastrowid
        
        # Add to active students
        active_students[student_id] = {
            'student_name': student_name,
            'class_id': class_id,
            'join_timestamp': join_timestamp,
            'active_app': 'Chrome',
            'session_id': session_id
        }
        
        # Emit student joined event
        socketio.emit('student_joined', {
            'student_id': student_id,
            'student_name': student_name,
            'class_id': class_id,
            'join_timestamp': join_timestamp,
            'session_id': session_id
        }, broadcast=True)
        
        return jsonify({
            "success": True, 
            "session_id": session_id,
            "join_timestamp": join_timestamp
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/student/disconnect', methods=['POST'])
def disconnect_student():
    """Handle student disconnect - remove from active list"""
    try:
        data = request.get_json()
        if not data or "student_id" not in data:
            return jsonify({"error": "student_id required"}), 400
        
        student_id = data["student_id"]
        
        # Get student info before removing
        student_name = 'Unknown'
        if student_id in active_students:
            student_name = active_students[student_id].get('student_name', 'Unknown')
            del active_students[student_id]
        
        # Update session in database
        cursor.execute("""
            UPDATE student_sessions 
            SET is_active = 0, session_end = CURRENT_TIMESTAMP 
            WHERE student_id = ? AND is_active = 1
        """, (student_id,))
        conn.commit()
        
        # Emit student disconnected event
        socketio.emit('student_disconnected', {
            'student_id': student_id,
            'student_name': student_name
        }, broadcast=True)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5050, allow_unsafe_werkzeug=True)
