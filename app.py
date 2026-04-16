import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False) # Admin, Teacher, Student
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100))
    dob = db.Column(db.String(20))
    roll_no = db.Column(db.String(50))

class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    dates = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to user
    user = db.relationship('User', backref=db.backref('leaves', lazy=True))

# Create Database and Admin
with app.app_context():
    db.create_all()
    # Check if admin exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(name='Administrator', role='Admin', username='admin', password='admin123')
        db.session.add(admin)
        db.session.commit()

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
    
    if role == 'Admin':
        teacher_count = User.query.filter_by(role='Teacher').count()
        student_count = User.query.filter_by(role='Student').count()
        pending_leaves = LeaveRequest.query.filter_by(status='Pending', role='Teacher').count()
        return render_template('admin/dashboard.html', teacher_count=teacher_count, student_count=student_count, pending_leaves=pending_leaves)
    
    elif role == 'Teacher':
        pending_student_leaves = LeaveRequest.query.filter_by(status='Pending', role='Student').count()
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

# Admin Routes
@app.route('/admin/teachers')
def manage_teachers():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    teachers = User.query.filter_by(role='Teacher').all()
    return render_template('admin/teachers.html', teachers=teachers)

@app.route('/admin/add_teacher', methods=['POST'])
def add_teacher():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    name = request.form.get('name')
    dept = request.form.get('department')
    
    if not name or not dept:
        flash('All fields are required!', 'warning')
        return redirect(url_for('manage_teachers'))
        
    # Check if username exists
    existing = User.query.filter_by(username=name).first()
    if existing:
        flash('Teacher name must be unique!', 'danger')
        return redirect(url_for('manage_teachers'))

    new_teacher = User(name=name, role='Teacher', username=name, password=dept, department=dept)
    db.session.add(new_teacher)
    db.session.commit()
    flash('Teacher added successfully!', 'success')
    return redirect(url_for('manage_teachers'))

@app.route('/admin/students')
def manage_students():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    students = User.query.filter_by(role='Student').all()
    return render_template('admin/students.html', students=students)

@app.route('/admin/add_student', methods=['POST'])
def add_student():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    name = request.form.get('name')
    roll_no = request.form.get('roll_no')
    dob = request.form.get('dob')
    
    if not name or not roll_no or not dob:
        flash('All fields are required!', 'warning')
        return redirect(url_for('manage_students'))

    # Check if username exists
    existing = User.query.filter_by(username=roll_no).first()
    if existing:
        flash('Roll number must be unique!', 'danger')
        return redirect(url_for('manage_students'))

    new_student = User(name=name, role='Student', username=roll_no, password=dob, roll_no=roll_no, dob=dob)
    db.session.add(new_student)
    db.session.commit()
    flash('Student added successfully!', 'success')
    return redirect(url_for('manage_students'))

@app.route('/admin/leaves')
def view_all_leaves():
    if session.get('role') != 'Admin': return redirect(url_for('login'))
    # Admin views all leaves
    leaves = LeaveRequest.query.all()
    return render_template('admin/leaves.html', leaves=leaves)

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
    leaves = LeaveRequest.query.filter_by(role='Student').all()
    return render_template('teacher/student_leaves.html', leaves=leaves)

# General Routes
@app.route('/apply_leave', methods=['GET', 'POST'])
def apply_leave():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        reason = request.form.get('reason')
        dates = request.form.get('dates')
        
        new_leave = LeaveRequest(user_id=session['user_id'], role=session['role'], reason=reason, dates=dates)
        db.session.add(new_leave)
        db.session.commit()
        flash('Leave request submitted!', 'success')
        return redirect(url_for('dashboard'))
    
    if session['role'] == 'Teacher':
        return render_template('teacher/apply_leave.html')
    else:
        return render_template('student/apply_leave.html')

@app.route('/update_leave/<int:leave_id>/<string:status>')
def update_leave(leave_id, status):
    if 'user_id' not in session: return redirect(url_for('login'))
    leave = LeaveRequest.query.get(leave_id)
    if not leave: return redirect(url_for('dashboard'))
    
    current_role = session.get('role')
    if current_role == 'Admin' and leave.role == 'Teacher':
        leave.status = status
    elif current_role == 'Teacher' and leave.role == 'Student':
        leave.status = status
    else:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('dashboard'))
        
    db.session.commit()
    flash(f'Leave {status} successfully!', 'info')
    return redirect(request.referrer)

if __name__ == '__main__':
    app.run(debug=True)
