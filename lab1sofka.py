class Student:

    def __init__(self, id, last_name, first_name, middle_name, date_of_birth, address, phone, faculty, course, group):
        self.id = id
        self.last_name = last_name
        self.first_name = first_name
        self.middle_name = middle_name
        self.date_of_birth = date_of_birth
        self.address = address
        self.phone = phone
        self._faculty = faculty 
        self.course = course
        self.group = group

    def __str__(self):
        return f"ID: {self.id}, Name: {self.last_name} {self.first_name} {self.middle_name}, Faculty: {self._faculty}, Course: {self.course}, Group: {self.group}"

    def __eq__(self, other):
        if isinstance(other, Student):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    @property
    def faculty(self):
        return self._faculty 

    @faculty.setter
    def faculty(self, value):
        self._faculty = value  


class University:

    def __init__(self):
        self.students = []

    def add_student(self, student):
        self.students.append(student)

    def print_students_by_faculty(self, faculty):
        print(f"\nList of students from the faculty '{faculty}':")
        for student in self.students:
            if student.faculty == faculty:
                print(student)

    def print_students_by_faculty_and_course(self):
        print("\nLists of students by faculty and course:")
        groupings = {}
        for student in self.students:
            key = (student.faculty, student.course)
            if key not in groupings:
                groupings[key] = []
            groupings[key].append(student)

        for (faculty, course), student_list in groupings.items():
            print(f"Faculty: {faculty}, Course: {course}")
            for student in student_list:
                print(f"  - {student.last_name} {student.first_name} {student.middle_name}")

    def print_students_born_after_year(self, year):
        print(f"\nList of students born after {year}:")
        for student in self.students:
            if int(student.date_of_birth[:4]) > year:
                print(student)

    def print_students_by_group(self, group):
        print(f"\nList of students from the group '{group}':")
        for student in self.students:
            if student.group == group:
                print(student)


if __name__ == "__main__":
    university = University()

    student1 = Student(1, "Ivanov", "Ivan", "Ivanovich", "2002-05-10", "Moscow", "8-916-123-45-67", "Informatics", 2, "I22")
    student2 = Student(2, "Petrov", "Petr", "Petrovich", "2001-08-15", "St. Petersburg", "8-921-987-65-43", "Informatics", 3, "I23")
    student3 = Student(3, "Sidorova", "Anna", "Sergeevna", "2003-02-20", "Kazan", "8-903-555-12-34", "Mathematics", 1, "23")
    student4 = Student(4, "Smirnov", "Dmitry", "Andreevich", "2002-11-01", "Novosibirsk", "8-950-777-88-99", "Informatics", 2, "I22")

    university.add_student(student1)
    university.add_student(student2)
    university.add_student(student3)
    university.add_student(student4)

    university.print_students_by_faculty("Informatics")
    university.print_students_by_faculty_and_course()
    university.print_students_born_after_year(2001)
    university.print_students_by_group("I22")