import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
import requests
import json
from werkzeug.utils import secure_filename
import threading
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI', 'sqlite:///database_v2.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Email Configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def send_approval_email(target_email, name, role, dates):
    try:
        msg = Message("Leave Request Approved",
                      recipients=[target_email])
        msg.body = f"Hello {name},\n\nYour leave request for {dates} as a {role} has been APPROVED.\n\nBest regards,\nCollege Leave Management System"
        
        # Send in a background thread to avoid slowing down the UI
        thread = threading.Thread(target=send_async_email, args=(msg,))
        thread.start()
        print(f"Approval email sent to {target_email}")
    except Exception as e:
        print(f"Error sending email: {e}")

def send_parent_notification(parent_email, student_name, dates):
    try:
        msg = Message(f"Leave Approved: {student_name}",
                      recipients=[parent_email])
        msg.body = f"Dear Parent,\n\nThis is to inform you that the leave request applied by your ward, {student_name}, for the dates {dates} has been APPROVED by the college.\n\nBest regards,\nCollege Leave Management System"
        
        thread = threading.Thread(target=send_async_email, args=(msg,))
        thread.start()
        print(f"Parent notification email sent to {parent_email}")
    except Exception as e:
        print(f"Error sending parent email: {e}")

def send_async_email(msg):
    with app.app_context():
        mail.send(msg)

def sendWhatsAppMessage(to_number, message):
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    if not account_sid or not auth_token:
        print("Twilio credentials not configured.")
        return
        
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    
    number = to_number.strip()
    if not number.startswith('+'):
        number = '+91' + number
    
    if not number.startswith('whatsapp:'):
        number = f"whatsapp:{number}"

    payload = {
        'To': number,
        'From': os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886'),
        'Body': message
    }
    
    try:
        response = requests.post(
            url,
            data=payload,
            auth=(account_sid, auth_token)
        )
        if response.status_code in [200, 201]:
            print(f"WhatsApp message sent successfully to {number}.")
        else:
            print(f"Failed to send WhatsApp message. Status: {response.status_code}, Error: {response.text}")
    except Exception as e:
        print(f"Exception occurred while sending WhatsApp message: {e}")

def notify_students_timetable_update(class_name, subject, day, period, teacher_name):
    students = User.query.filter_by(role='Student', department=class_name).all()
    if not students:
        return
    message = f"Timetable Update 📅\nClass: {class_name}\nSubject: {subject}\nDay: {day}\nPeriod: {period}\nTeacher: {teacher_name}"
    for student in students:
        if student.phone:
            threading.Thread(target=sendWhatsAppMessage, args=(student.phone, message)).start()

def is_absent_today(date_str):
    """
    Checks if today's date falls within the provided date_str.
    Expects formats like 'DD-MM-YYYY' or 'DD-MM-YYYY to DD-MM-YYYY'
    """
    from datetime import date
    today = date.today()
    
    try:
        if 'to' in date_str.lower():
            start_str, end_str = date_str.lower().split('to')
            start_date = datetime.strptime(start_str.strip(), '%d-%m-%Y').date()
            end_date = datetime.strptime(end_str.strip(), '%d-%m-%Y').date()
            return start_date <= today <= end_date
        else:
            single_date = datetime.strptime(date_str.strip(), '%d-%m-%Y').date()
            return single_date == today
    except:
        # Fallback: simple string inclusion check if format is non-standard
        today_str = today.strftime('%d-%m-%Y')
        return today_str in date_str

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False) # Admin, Teacher, Student
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100)) # Dept for Teacher, Class for Student
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    dob = db.Column(db.String(20))
    roll_no = db.Column(db.String(50))
    parent_email = db.Column(db.String(120))

class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    dates = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.String(20)) # Added for same-day time checks
    document_path = db.Column(db.String(200)) # Path to uploaded file
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    remark = db.Column(db.Text, nullable=True) # Comment/Remark by Admin or Teacher
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to user
    user = db.relationship('User', backref=db.backref('leaves', lazy=True))

class TeacherTimetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day = db.Column(db.String(20), nullable=False) # Monday, Tuesday, etc.
    period = db.Column(db.Integer, nullable=False) # 1, 2, 3, etc.
    subject = db.Column(db.String(100), nullable=False)
    
    teacher = db.relationship('User', backref=db.backref('timetable', lazy=True))

# Create Database and Admin
with app.app_context():
    db.create_all()
    # Check if admin exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(name='Administrator', role='Admin', username='admin', password='admin123')
        db.session.add(admin)
        db.session.commit()
    
    # Always sync users from JSON on startup to keep data fresh
    import json
    json_path = os.path.join(app.root_path, 'users_data.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Clear existing non-admin users to remove "fake" or old data
            # This ensures the database EXACTLY matches the JSON file
            User.query.filter(User.role != 'Admin').delete()
            
            for user_data in data:
                new_user = User(
                    name=user_data['name'],
                    role=user_data['role'],
                    username=user_data['username'],
                    password=user_data['password'],
                    department=user_data['department'],
                    email=user_data.get('email'),
                    phone=user_data.get('phone'),
                    dob=user_data.get('dob'),
                    roll_no=user_data.get('roll_no'),
                    parent_email=user_data.get('parent_email')
                )
                db.session.add(new_user)
            
            db.session.commit()
            print("Successfully synchronized users from JSON (Clean Sync).")
        except Exception as e:
            print(f"Error syncing JSON: {e}")
            db.session.rollback()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            session['department'] = user.department
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'danger')
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    role = session['role']
    user = User.query.get(session['user_id'])
    
    # Refresh session data from DB to ensure it's not None
    if user:
        session['department'] = user.department
        session['name'] = user.name
    
    if role == 'Admin':
        teacher_count = User.query.filter_by(role='Teacher').count()
        student_count = User.query.filter_by(role='Student').count()
        pending_leaves = LeaveRequest.query.filter(
            ((LeaveRequest.role == 'Teacher') & (LeaveRequest.status == 'Pending')) |
            (LeaveRequest.status == 'Forwarded to Admin')
        ).count()
        return render_template('admin/dashboard.html', teacher_count=teacher_count, student_count=student_count, pending_leaves=pending_leaves)
    
    elif role == 'Teacher':
        # Find mentored classes for this teacher
        current_teacher_name = session.get('name')
        mentored_classes = []
        try:
            mentors_path = os.path.join(app.root_path, 'mentors_data.json')
            if os.path.exists(mentors_path):
                with open(mentors_path, 'r') as f:
                    mentors_data = json.load(f)
                for item in mentors_data:
                    if item['mentor1'] == current_teacher_name or item['mentor2'] == current_teacher_name:
                        mentored_classes.append(item['class_name'])
        except Exception as e:
            print(f"Error loading mentors in dashboard: {e}")

        # Filter count for mentored classes only
        pending_student_leaves = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id)\
                                .filter(LeaveRequest.status == 'Pending', LeaveRequest.role == 'Student')\
                                .filter(User.department.in_(mentored_classes)).count() if mentored_classes else 0
                                
        my_leaves = LeaveRequest.query.filter_by(user_id=session['user_id']).all()
        return render_template('teacher/dashboard.html', pending_student_leaves=pending_student_leaves, my_leaves=my_leaves)
    
    elif role == 'Student':
        my_leaves = LeaveRequest.query.filter_by(user_id=session['user_id']).all()
        return render_template('student/dashboard.html', my_leaves=my_leaves)
        
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Socket.IO Connection and Rooms
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        if session['role'] == 'Admin':
            join_room('admin_room')
        elif session['role'] == 'Teacher':
            # Join room for individual notifications
            join_room(f"user_{session['user_id']}")
            # Join rooms for mentored classes
            current_teacher_name = session.get('name')
            try:
                mentors_path = os.path.join(app.root_path, 'mentors_data.json')
                if os.path.exists(mentors_path):
                    with open(mentors_path, 'r') as f:
                        mentors_data = json.load(f)
                    for item in mentors_data:
                        if item['mentor1'] == current_teacher_name or item['mentor2'] == current_teacher_name:
                            join_room(f"mentor_{item['class_name']}")
                            print(f"Teacher {current_teacher_name} joined room: mentor_{item['class_name']}")
            except Exception as e:
                print(f"Error joining mentor rooms: {e}")
        else:
            join_room(f"user_{session['user_id']}")
    print(f"Client connected: {request.sid}")

# Admin Routes
@app.route('/admin/teachers')
def manage_teachers():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    teachers = User.query.filter_by(role='Teacher').all()
    return render_template('admin/teachers.html', teachers=teachers)

@app.route('/admin/students')
def manage_students():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    students = User.query.filter_by(role='Student').all()
    return render_template('admin/students.html', students=students)

@app.route('/admin/leaves')
def view_all_leaves():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    # Admin views: All Teacher leaves and ONLY Forwarded Student leaves (for action)
    leaves = LeaveRequest.query.filter(
        (LeaveRequest.role == 'Teacher') | 
        (LeaveRequest.status == 'Forwarded to Admin')
    ).order_by(LeaveRequest.created_at.desc()).all()
    return render_template('admin/leaves.html', leaves=leaves)

@app.route('/admin/absentees')
def view_absentees():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    
    # Get all approved leaves
    approved_leaves = LeaveRequest.query.filter_by(status='Approved').all()
    
    absent_teachers = {}
    absent_students = {}
    
    for leave in approved_leaves:
        if leave.role == 'Teacher':
            dept = leave.user.department
            if dept not in absent_teachers: absent_teachers[dept] = []
            absent_teachers[dept].append(leave)
        else:
            cls = leave.user.department # department field stores Class for students
            if cls not in absent_students: absent_students[cls] = []
            absent_students[cls].append(leave)
                
    return render_template('admin/absentees.html', 
                            absent_teachers=absent_teachers, 
                            absent_students=absent_students)

@app.route('/admin/reports')
def leave_reports():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    
    all_leaves = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()
    
    report_teachers = {}
    report_students = {}
    
    for leave in all_leaves:
        if leave.role == 'Teacher':
            dept = leave.user.department or 'Unknown'
            if dept not in report_teachers: report_teachers[dept] = []
            report_teachers[dept].append(leave)
        else:
            cls = leave.user.department or 'Unknown'
            if cls not in report_students: report_students[cls] = []
            report_students[cls].append(leave)
            
    return render_template('admin/reports.html', 
                            report_teachers=report_teachers, 
                            report_students=report_students)

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    user = User.query.get(user_id)
    if user and user.role != 'Admin':
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully!', 'success')
    return redirect(request.referrer)

# Teacher Routes
@app.route('/teacher/student_leaves')
def teacher_student_leaves():
    if session.get('role') != 'Teacher': return redirect(url_for('login'))
    
    current_teacher_name = session.get('name')
    
    # Load mentors data to find which class this teacher mentors
    import json
    mentors_path = os.path.join(app.root_path, 'mentors_data.json')
    mentored_classes = []
    
    if os.path.exists(mentors_path):
        try:
            with open(mentors_path, 'r') as f:
                mentors_data = json.load(f)
            for item in mentors_data:
                if item['mentor1'] == current_teacher_name or item['mentor2'] == current_teacher_name:
                    mentored_classes.append(item['class_name'])
        except Exception as e:
            print(f"Error reading mentors: {e}")

    # If the teacher is not a mentor for any class, they see no student leaves
    if not mentored_classes:
        return render_template('teacher/student_leaves.html', leaves=[], mentored_classes=[])

    # Filter leaves: Student requests where student department is in mentored_classes
    leaves = LeaveRequest.query.join(User, LeaveRequest.user_id == User.id)\
                               .filter(User.role == 'Student')\
                               .filter(User.department.in_(mentored_classes)).all()
                               
    return render_template('teacher/student_leaves.html', leaves=leaves, mentored_classes=mentored_classes)

# General Routes
@app.route('/apply_leave', methods=['GET', 'POST'])
def apply_leave():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        reason = request.form.get('reason')
        dates = request.form.get('dates')
        start_time_val = request.form.get('start_time') # Optional time field
        file = request.files.get('document')
        
        # Date Validation: Pattern and Past Dates
        from datetime import date
        today = date.today()
        import re
        # Regex for DD-MM-YYYY or DD-MM-YYYY to DD-MM-YYYY
        pattern = r'^\d{2}-\d{2}-\d{4}( to \d{2}-\d{2}-\d{4})?$'
        
        if not re.match(pattern, dates.strip()):
            flash('Invalid date pattern! Please use DD-MM-YYYY or DD-MM-YYYY to DD-MM-YYYY', 'warning')
            return redirect(request.referrer)

        try:
            if ' to ' in dates.lower():
                start_str = dates.lower().split('to')[0].strip()
            else:
                start_str = dates.strip()
            
            # Use %d-%m-%Y for parsing
            requested_start = datetime.strptime(start_str, '%d-%m-%Y').date()
            if requested_start < today:
                flash(f'Cannot apply for past dates! Today is {today.strftime("%d-%m-%Y")}.', 'warning')
                return redirect(request.referrer)
            
            # Same-Day Leave Rules
            if requested_start == today:
                now_dt = datetime.now()
                now_time = now_dt.time()
                
                # 1. Student Rule: Before 9:00 AM
                if session.get('role') == 'Student':
                    cutoff_time = datetime.strptime("09:00:00", "%H:%M:%S").time()
                    if now_time >= cutoff_time:
                        flash('Same-day student leave must be applied before 9:00 AM!', 'danger')
                        return redirect(request.referrer)
                
                # 2. Teacher Rule: 1-hour Gap Rule
                elif session.get('role') == 'Teacher' and start_time_val:
                    try:
                        # Parse user's requested leave time (e.g. "12:00")
                        leave_dt = datetime.strptime(f"{today.strftime('%d-%m-%Y')} {start_time_val}", "%d-%m-%Y %H:%M")
                        
                        # Calculate time difference
                        time_diff = leave_dt - now_dt
                        diff_minutes = time_diff.total_seconds() / 60
                        
                        if diff_minutes < 60:
                            flash('Same-day teacher leave must be applied at least 1 hour before the leave starts! In case of any emergency, please contact the Administrator.', 'danger')
                            return redirect(request.referrer)
                    except ValueError:
                        flash('Invalid time format! Please use HH:MM (24-hour format)', 'warning')
                        return redirect(request.referrer)
        except Exception as e:
            flash(f'Error parsing dates: {e}', 'warning')
            return redirect(request.referrer)
        
        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{session['user_id']}_{datetime.now().timestamp()}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        new_leave = LeaveRequest(
            user_id=session['user_id'], 
            role=session['role'], 
            reason=reason, 
            dates=dates, 
            start_time=start_time_val,
            document_path=filename
        )
        db.session.add(new_leave)
        db.session.commit()
        
        # Real-time notification for Admin
        socketio.emit('new_leave_submitted', {
            'id': new_leave.id,
            'name': session['name'],
            'role': session['role'],
            'dates': dates,
            'reason': reason,
            'status': new_leave.status
        }, to='admin_room')
        
        # Real-time notification for Mentors
        if session['role'] == 'Student':
            student_class = session.get('department') # 'department' field stores the class (e.g., IIBCA)
            
            # Get user roll no
            user = User.query.get(session['user_id'])
            
            socketio.emit('new_student_leave', {
                'id': new_leave.id,
                'student_name': session['name'],
                'student_roll_no': user.roll_no,
                'student_class': student_class,
                'dates': dates,
                'reason': reason,
                'document_path': filename,
                'status': new_leave.status
            }, to=f"mentor_{student_class}")
        
        flash('Leave request submitted!', 'success')
        return redirect(url_for('dashboard'))
    
    if session['role'] == 'Teacher':
        return render_template('teacher/apply_leave.html')
    else:
        return render_template('student/apply_leave.html')

<<<<<<< HEAD
def get_weekdays_from_dates(dates_str):
    from datetime import datetime, timedelta
    weekdays = []
    try:
        if ' to ' in dates_str.lower():
            start_str, end_str = dates_str.lower().split('to')
            start_date = datetime.strptime(start_str.strip(), '%d-%m-%Y').date()
            end_date = datetime.strptime(end_str.strip(), '%d-%m-%Y').date()
            
            delta = timedelta(days=1)
            while start_date <= end_date:
                weekdays.append((start_date.strftime('%A'), start_date.strftime('%d-%m-%Y')))
                start_date += delta
        else:
            single_date = datetime.strptime(dates_str.strip(), '%d-%m-%Y').date()
            weekdays.append((single_date.strftime('%A'), single_date.strftime('%d-%m-%Y')))
    except Exception as e:
        print(f"Error parsing dates for weekdays: {e}")
    return weekdays

def get_mentors_for_class(class_name):
    """Returns list of (teacher_id, teacher_name) for mentors of a given class."""
    mentors_path = os.path.join(app.root_path, 'mentors_data.json')
    mentor_users = []
    if not os.path.exists(mentors_path):
        return mentor_users
    try:
        with open(mentors_path, 'r') as f:
            mentors_data = json.load(f)
        for item in mentors_data:
            if item['class_name'] == class_name:
                for mentor_key in ['mentor1', 'mentor2']:
                    mentor_name = item.get(mentor_key)
                    if mentor_name:
                        mentor_user = User.query.filter_by(name=mentor_name, role='Teacher').first()
                        if mentor_user:
                            mentor_users.append((mentor_user.id, mentor_user.name))
    except Exception as e:
        print(f"Error loading mentors for notification: {e}")
    return mentor_users

def notify_teachers_for_student_absence(leave):
    weekdays_and_dates = get_weekdays_from_dates(leave.dates)
    if not weekdays_and_dates: return
    
    student_class = leave.user.department
    mapping = get_class_subject_mapping()
    class_subjects = mapping.get(student_class, [])
    
    # --- TIER 1: Always notify Class Mentors ---
    mentor_ids_notified = set()
    mentors = get_mentors_for_class(student_class)
    for mentor_id, mentor_name in mentors:
        mentor_ids_notified.add(mentor_id)
        msg = f"FYI: Your mentee {leave.user.name} ({student_class}) has an approved leave on {leave.dates}."
        socketio.emit('student_absence_alert', {
            'message': msg,
            'type': 'info'
        }, to=f"user_{mentor_id}")
        print(f"[Absence] Mentor notified: {mentor_name} (id={mentor_id}) for student {leave.user.name}")
    
    if not class_subjects:
        print(f"[Absence] No class_subjects found for class '{student_class}', skipping timetable check.")
        return
    
    # --- TIER 2: Notify Subject Teachers from Timetable ---
    for day_name, date_str in weekdays_and_dates:
        timetable_records = TeacherTimetable.query.filter(
            TeacherTimetable.day == day_name,
            TeacherTimetable.subject.in_(class_subjects)
        ).all()
        
        print(f"[Absence] Timetable check for {student_class} on {day_name} ({date_str}): {len(timetable_records)} record(s).")
        
        teacher_notifications = {}
        for record in timetable_records:
            if record.teacher_id not in teacher_notifications:
                teacher_notifications[record.teacher_id] = []
            if record.subject not in teacher_notifications[record.teacher_id]:
                teacher_notifications[record.teacher_id].append(record.subject)
            
        for teacher_id, subjects in teacher_notifications.items():
            # Skip if mentor was already notified with the general message
            subjects_str = ", ".join(subjects)
            msg = f"Alert: {leave.user.name} ({student_class}) will be absent on {date_str}. They will miss your {subjects_str} class(es)."
            
            socketio.emit('student_absence_alert', {
                'message': msg,
                'type': 'warning'
            }, to=f"user_{teacher_id}")
            print(f"[Absence] Subject teacher notified: id={teacher_id}, subjects={subjects_str}")

@app.route('/update_leave/<int:leave_id>/<string:status>')
=======
@app.route('/update_leave/<int:leave_id>/<string:status>', methods=['GET', 'POST'])
>>>>>>> deefe493211b605a07e5354395c2516289ed07a7
def update_leave(leave_id, status):
    if 'user_id' not in session: return redirect(url_for('login'))
    leave = LeaveRequest.query.get(leave_id)
    if not leave: return redirect(url_for('dashboard'))
    
    current_role = session.get('role')
    
    # Admin can approve/reject Teacher leaves OR Student leaves forwarded to them
    if current_role == 'Admin':
        if leave.role == 'Teacher' or leave.status == 'Forwarded to Admin':
            leave.status = status
        else:
            flash('Unauthorized for this request', 'danger')
            return redirect(url_for('dashboard'))
            
    # Teacher (Mentor) can approve/reject/forward Student leaves
    elif current_role == 'Teacher' and leave.role == 'Student':
        leave.status = status
    else:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('dashboard'))
        
    remark = request.values.get('remark')
    if remark:
        leave.remark = remark
        
    db.session.commit()
    
    # Send Email Notification if Approved
    if status == 'Approved':
        # Notify user (Student or Teacher)
        if leave.user.email:
            send_approval_email(leave.user.email, leave.user.name, leave.role, leave.dates)
        
        # Notify Parent if Student
        if leave.role == 'Student' and leave.user.parent_email:
            send_parent_notification(leave.user.parent_email, leave.user.name, leave.dates)
            
        # Notify Teachers about Student Absence
        if leave.role == 'Student':
            notify_teachers_for_student_absence(leave)
            
    # Send WhatsApp Notification for Approved or Rejected Leave to Student
    if leave.role == 'Student' and status in ['Approved', 'Rejected']:
        if leave.user.phone:
            wa_message = f"Leave Update 📅\nYour leave request for {leave.dates} has been {status}."
            threading.Thread(target=sendWhatsAppMessage, args=(leave.user.phone, wa_message)).start()
        
    flash(f'Leave updated to {status} successfully!', 'info')
    
    # Real-time notification for User and Admin
    update_data = {
        'id': leave_id,
        'status': status,
<<<<<<< HEAD
        'message': f"Leave request for {leave.user.name} has been {status}.",
        'user_id': leave.user_id,
        'role': leave.role
=======
        'remark': leave.remark,
        'message': f"Leave request for {leave.user.name} has been {status}."
>>>>>>> deefe493211b605a07e5354395c2516289ed07a7
    }
    socketio.emit('leave_status_changed', update_data, to=f"user_{leave.user_id}")
    socketio.emit('leave_status_changed', update_data, to='admin_room')
    
    # Send status change to mentors if it's a student
    if leave.role == 'Student':
        student_class = leave.user.department
        socketio.emit('leave_status_changed', update_data, to=f"mentor_{student_class}")
    
    return redirect(request.referrer)

# Timetable Management Routes
def get_class_subject_mapping():
    json_path = os.path.join(app.root_path, 'class_subjects.json')
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            return json.load(f)
    return {}

def get_class_from_subject(subject_name):
    if not subject_name: return None
    mapping = get_class_subject_mapping()
    search_sub = subject_name.strip().lower()
    for class_name, subjects in mapping.items():
        # Check case-insensitively
        if any(search_sub == s.strip().lower() for s in subjects):
            return class_name
    return None

@app.route('/teacher/timetable')
def teacher_timetable():
    if session.get('role') != 'Teacher': return redirect(url_for('login'))
    
    teacher_id = session.get('user_id')
    timetable_records = TeacherTimetable.query.filter_by(teacher_id=teacher_id).all()
    
    # Organize into a dict for easy access: {day: {period: subject}}
    timetable_data = {}
    for record in timetable_records:
        if record.day not in timetable_data: timetable_data[record.day] = {}
        timetable_data[record.day][record.period] = record.subject
        
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    periods = range(1, 8) # 7 periods
    
    mapping = get_class_subject_mapping()
    all_subjects = []
    for subjects in mapping.values():
        all_subjects.extend(subjects)
    all_subjects = sorted(list(set(all_subjects)))

    # Identify the teacher's mentored class
    mentor_class = None
    mentors_path = os.path.join(app.root_path, 'mentors_data.json')
    if os.path.exists(mentors_path):
        with open(mentors_path, 'r') as f:
            mentors_data = json.load(f)
        teacher_name = (session.get('name') or "").strip().lower()
        for mentor_info in mentors_data:
            if (mentor_info.get('mentor1') or "").strip().lower() == teacher_name or \
               (mentor_info.get('mentor2') or "").strip().lower() == teacher_name:
                mentor_class = mentor_info['class_name']
                break
    
    return render_template('teacher/timetable.html', 
                           timetable_data=timetable_data, 
                           days=days, 
                           periods=periods,
                           all_subjects=all_subjects,
                           class_mapping=mapping,
                           mentor_class=mentor_class)

@app.route('/admin/subjects', methods=['GET', 'POST'])
def manage_subjects():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    
    mapping = get_class_subject_mapping()
    
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        new_class_name = request.form.get('new_class_name', '').strip()
        new_subject = request.form.get('subject').strip()
        
        # Use existing class if selected, otherwise use new class name
        final_class = class_name if class_name else new_class_name
        
        if final_class and new_subject:
            if final_class not in mapping:
                mapping[final_class] = []
            
            if new_subject not in mapping[final_class]:
                mapping[final_class].append(new_subject)
                
                # Save back to JSON
                json_path = os.path.join(app.root_path, 'class_subjects.json')
                with open(json_path, 'w') as f:
                    json.dump(mapping, f, indent=2)
                
                flash(f'Subject "{new_subject}" added to {final_class}!', 'success')
            else:
                flash('Subject already exists for this class.', 'warning')
        else:
            flash('Please provide both Class Name and Subject.', 'danger')
        return redirect(url_for('manage_subjects'))
        
    return render_template('admin/subjects.html', mapping=mapping)

@app.route('/api/delete_subject', methods=['POST'])
def delete_subject():
    if session.get('role') != 'Admin': return jsonify({'success': False}), 403
    data = request.json
    class_name = data.get('class_name')
    subject = data.get('subject')
    
    mapping = get_class_subject_mapping()
    if class_name in mapping and subject in mapping[class_name]:
        mapping[class_name].remove(subject)
        json_path = os.path.join(app.root_path, 'class_subjects.json')
        with open(json_path, 'w') as f:
            json.dump(mapping, f, indent=2)
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/api/save_timetable', methods=['POST'])
def save_timetable():
    if session.get('role') != 'Teacher': return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    print(f"DEBUG: Received save_timetable request: {data}")
    teacher_id = session.get('user_id')
    day = data.get('day')
    try:
        period = int(data.get('period'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid period data'}), 400
    subject = data.get('subject')
    
    if not day or not period:
        return jsonify({'success': False, 'message': 'Missing data'}), 400

    # 1. Determine Target Class
    mapping = get_class_subject_mapping()
    target_class = data.get('class_name') # Explicit selection from user
    official_subject = subject
    
    if subject:
        search_sub = subject.strip().lower()
        
        # 2. Identify the teacher's mentored class
        user_mentored_class = None
        mentors_path = os.path.join(app.root_path, 'mentors_data.json')
        if os.path.exists(mentors_path):
            with open(mentors_path, 'r') as f:
                mentors_data = json.load(f)
            teacher_name = (session.get('name') or "").strip().lower()
            for mentor_info in mentors_data:
                m1 = (mentor_info.get('mentor1') or "").strip().lower()
                m2 = (mentor_info.get('mentor2') or "").strip().lower()
                if m1 == teacher_name or m2 == teacher_name:
                    user_mentored_class = mentor_info['class_name']
                    break

        # 3. Determine Target Class
        if not target_class:
            # Check mentored class FIRST to prevent ambiguity
            if user_mentored_class and user_mentored_class in mapping:
                for s in mapping[user_mentored_class]:
                    if search_sub == s.strip().lower():
                        target_class = user_mentored_class
                        official_subject = s
                        break
            
            # If not in mentored class, search ALL classes
            if not target_class:
                for c_name, subjects in mapping.items():
                    for s in subjects:
                        if search_sub == s.strip().lower():
                            target_class = c_name
                            official_subject = s
                            break
                    if target_class: break
        
        # 4. Final Fallback: First class in their department, or first class in list, or "General"
        if not target_class:
            user_dept = session.get('department')
            if user_dept:
                for c_name in mapping.keys():
                    if user_dept.lower() in c_name.lower():
                        target_class = c_name
                        break
        
        if not target_class:
            target_class = list(mapping.keys())[0] if mapping.keys() else "General"
            
        print(f"Final determined class for {subject}: {target_class}")
        
        # 5. Auto-add to curriculum if it's missing from target class
        if target_class not in mapping: mapping[target_class] = []
        if not any(s.strip().lower() == search_sub for s in mapping[target_class]):
            mapping[target_class].append(subject)
            json_path = os.path.join(app.root_path, 'class_subjects.json')
            with open(json_path, 'w') as f:
                json.dump(mapping, f, indent=2)
            official_subject = subject
            print(f"Auto-added {subject} to class {target_class}")
        else:
            # If it IS there, find the official casing
            for s in mapping[target_class]:
                if s.strip().lower() == search_sub:
                    official_subject = s
                    break

        # Now we have final class_name and official_subject
        class_name = target_class
            
        # Update search subjects to use official names for database query
        mapping = get_class_subject_mapping()
        class_subjects = mapping.get(class_name, [])
        
        existing_class_record = TeacherTimetable.query.filter(
            TeacherTimetable.day == day,
            TeacherTimetable.period == period,
            TeacherTimetable.subject.in_(class_subjects),
            TeacherTimetable.teacher_id != teacher_id
        ).first()
        
        if existing_class_record:
            return jsonify({'success': False, 'message': f'Class {class_name} is busy with {existing_class_record.subject} (Teacher: {existing_class_record.teacher.name})'}), 400

    # Find or create record
    record = TeacherTimetable.query.filter_by(teacher_id=teacher_id, day=day, period=period).first()
    
    if subject:
        if record:
            record.subject = official_subject
        else:
            new_record = TeacherTimetable(teacher_id=teacher_id, day=day, period=period, subject=official_subject)
            db.session.add(new_record)
    else:
        # If subject is empty/None, remove the record
        if record:
            db.session.delete(record)
            
    db.session.commit()

    # Trigger WhatsApp notification for timetable update
    if subject and class_name:
        teacher_name = session.get('name')
        notify_students_timetable_update(class_name, official_subject, day, period, teacher_name)
    return jsonify({'success': True, 'class_name': class_name})

@app.route('/student/timetable')
def student_timetable():
    if session.get('role') != 'Student': return redirect(url_for('login'))
    
    student = User.query.get(session.get('user_id'))
    student_class = student.department # department field stores Class for students
    
    # Get subjects for this class
    mapping = get_class_subject_mapping()
    class_subjects = mapping.get(student_class, [])
    
    # Fetch all teacher timetable records that involve these subjects
    timetable_records = TeacherTimetable.query.filter(TeacherTimetable.subject.in_(class_subjects)).all()
    
    # Organize: {day: {period: {subject: subject, teacher: teacher_name}}}
    timetable_data = {}
    for record in timetable_records:
        if record.day not in timetable_data: timetable_data[record.day] = {}
        timetable_data[record.day][record.period] = {
            'subject': record.subject,
            'teacher': record.teacher.name
        }
        
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    periods = range(1, 8)
    
    return render_template('student/timetable.html', 
                           timetable_data=timetable_data, 
                           days=days, 
                           periods=periods,
                           student_class=student_class)

# AI Integration with Ollama
@app.route('/ai/ask', methods=['POST'])
def ai_ask():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_query = request.json.get('query')
    if not user_query:
        return jsonify({'error': 'No query provided'}), 400

    role = session.get('role')
    user_name = session.get('name')
    
    # System prompt to give context
    system_prompt = f"You are an AI assistant for a College Leave Management System. The current user is {user_name} with the role of {role}. Answer concisely."
    
    try:
        # Calling local Ollama API (Assumes llama3 is installed, fallback to llama2)
        response = requests.post('http://localhost:11434/api/generate', 
            json={
                'model': 'llama3', 
                'prompt': f"{system_prompt}\nUser: {user_query}",
                'stream': False
            }, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return jsonify({'response': result['response']})
        else:
            return jsonify({'error': 'Ollama server error'}), 500
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Ollama not running. Please start Ollama on your machine.'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
