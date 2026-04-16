import json
import random

def generate_data():
    data = []
    
    first_names = ["Arjun", "Aditi", "Rohan", "Sanya", "Vikram", "Neha", "Ishaan", "Priya", "Rahul", "Ananya", 
                   "Karan", "Meera", "Siddharth", "Tanvi", "Akash", "Riya", "Varun", "Kavya", "Abhishek", "Sneha",
                   "Manish", "Pooja", "Suresh", "Anita", "Rajesh", "Sunita", "Vijay", "Lata", "Ramesh", "Geeta"]
    last_names = ["Sharma", "Verma", "Gupta", "Malhotra", "Kapoor", "Singh", "Reddy", "Patel", "Iyer", "Nair",
                  "Joshi", "Chawla", "Deshmukh", "Choudhury", "Das", "Bose", "Kulkarni", "Prasad", "Maurya", "Yadav"]

    def get_real_name():
        return f"{random.choice(first_names)} {random.choice(last_names)}"

    # Teachers
    teacher_depts = ["Computer Science", "Business Administration", "Commerce", "Language"]
    used_teacher_names = set()
    for dept in teacher_depts:
        for i in range(1, 11):
            while True:
                name = get_real_name()
                if name not in used_teacher_names:
                    used_teacher_names.add(name)
                    break
            
            dob = f"{random.randint(1975, 1995)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
            # Teacher username = name, password = dept
            data.append({
                "name": name,
                "role": "Teacher",
                "username": name,
                "password": dept,
                "department": dept,
                "email": f"{name.lower().replace(' ', '.')}@college.edu",
                "phone": f"{random.randint(700, 999)}{random.randint(1000000, 9999999)}",
                "dob": dob,
                "roll_no": None
            })
            
    # Students
    student_classes = ["IBCA", "IIBCA", "IIIBCA", "IBBA", "IIBBA", "IIIBBA", "IBCOM", "IIBCOM", "IIIBCOM"]
    used_roll_nos = set()
    for cls in student_classes:
        for i in range(1, 11):
            roll = f"{cls}{str(i).zfill(2)}"
            name = get_real_name()
            dob = f"{random.randint(2003, 2006)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
            data.append({
                "name": name,
                "role": "Student",
                "username": roll,
                "password": dob,
                "department": cls,
                "email": f"{name.lower().replace(' ', '.')}@student.college.edu",
                "phone": f"{random.randint(600, 999)}{random.randint(1000000, 9999999)}",
                "dob": dob,
                "roll_no": roll
            })
            
    return data

if __name__ == "__main__":
    final_data = generate_data()
    with open("c:/D/Code_Predictors/leave_system/users_data.json", "w") as f:
        json.dump(final_data, f, indent=4)
    print(f"Generated {len(final_data)} users.")
