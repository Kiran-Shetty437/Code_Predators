import json

def assign_mentors():
    # Load existing users to get real teacher names
    with open("c:/D/Code_Predictors/leave_system/users_data.json", "r") as f:
        users = json.load(f)
    
    # Categorize teachers by department
    teachers_by_dept = {
        "Computer Science": [],
        "Business Administration": [],
        "Commerce": [],
        "Language": []
    }
    for u in users:
        if u['role'] == 'Teacher':
            teachers_by_dept[u['department']].append(u['name'])
            
    # Assign Mentors to Classes
    mapping = [
        # BCA Classes (Computer Science Teachers)
        {"class": "IBCA", "dept": "Computer Science"},
        {"class": "IIBCA", "dept": "Computer Science"},
        {"class": "IIIBCA", "dept": "Computer Science"},
        # BBA Classes (Business Administration Teachers)
        {"class": "IBBA", "dept": "Business Administration"},
        {"class": "IIBBA", "dept": "Business Administration"},
        {"class": "IIIBBA", "dept": "Business Administration"},
        # BCOM Classes (Commerce Teachers)
        {"class": "IBCOM", "dept": "Commerce"},
        {"class": "IIBCOM", "dept": "Commerce"},
        {"class": "IIIBCOM", "dept": "Commerce"}
    ]
    
    mentors_json = []
    
    # Track used teachers to ensure one teacher per class
    used_teachers = set()
    
    for item in mapping:
        dept_teachers = [t for t in teachers_by_dept[item['dept']] if t not in used_teachers]
        
        # Pick 2 mentors for each class
        mentor1 = dept_teachers[0]
        mentor2 = dept_teachers[1]
        
        used_teachers.add(mentor1)
        used_teachers.add(mentor2)
        
        mentors_json.append({
            "class_name": item['class'],
            "mentor1": mentor1,
            "mentor2": mentor2
        })
        
    return mentors_json

if __name__ == "__main__":
    data = assign_mentors()
    with open("c:/D/Code_Predictors/leave_system/mentors_data.json", "w") as f:
        json.dump(data, f, indent=4)
    print("Mentors data generated successfully.")
