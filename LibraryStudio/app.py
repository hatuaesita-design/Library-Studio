from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import re
from datetime import date, datetime, timedelta

app = Flask(__name__)

DATA_FILE = "library_data.json"


# -------------------- BOOK CLASS --------------------

class Book:
    def __init__(
        self,
        book_id,
        title,
        author,
        available=True,
        issued_count=0,
        issued_to="",
        issue_date="",
        due_date="",
        issued_student_ids=None
    ):
        self.book_id = str(book_id)
        self.title = title
        self.author = author
        self.available = available
        self.issued_count = issued_count
        self.issued_to = str(issued_to)
        self.issue_date = str(issue_date or "")
        self.due_date = str(due_date or "")
        self.issued_student_ids = list(issued_student_ids or [])


# -------------------- STUDENT CLASS --------------------

class Student:
    def __init__(self, student_id, name):
        self.student_id = str(student_id)
        self.name = name


# -------------------- LIBRARY CLASS --------------------

class Library:
    def __init__(self):
        self.books = []
        self.students = []
        self.load_data()

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return

        try:
            with open(DATA_FILE, "r") as file:
                data = json.load(file)

            self.books = [
                Book(
                    book["book_id"],
                    book["title"],
                    book["author"],
                    book.get("available", True),
                    book.get("issued_count", 0),
                    book.get("issued_to", ""),
                    book.get("issue_date", ""),
                    book.get("due_date", ""),
                    book.get("issued_student_ids", [])
                )
                for book in data.get("books", [])
            ]

            self.students = [
                Student(student["student_id"], student["name"])
                for student in data.get("students", [])
            ]

        except (json.JSONDecodeError, KeyError, TypeError):
            self.books = []
            self.students = []
            print("Warning: Could not read library_data.json.")

    def save_data(self):
        data = {
            "books": [
                {
                    "book_id": book.book_id,
                    "title": book.title,
                    "author": book.author,
                    "available": book.available,
                    "issued_count": book.issued_count,
                    "issued_to": book.issued_to,
                    "issue_date": book.issue_date,
                    "due_date": book.due_date,
                    "issued_student_ids": book.issued_student_ids
                }
                for book in self.books
            ],
            "students": [
                {
                    "student_id": student.student_id,
                    "name": student.name
                }
                for student in self.students
            ]
        }

        with open(DATA_FILE, "w") as file:
            json.dump(data, file, indent=4)

    def add_book(self, book_id, title, author):
        if any(book.book_id == book_id for book in self.books):
            return "Book ID already exists."

        self.books.append(Book(book_id, title, author))
        self.save_data()
        return "Book added successfully."

    def add_student(self, student_id, name):
        if any(s.student_id == student_id for s in self.students):
            return "Student ID already exists."

        self.students.append(Student(student_id, name))
        self.save_data()
        return "Student added successfully."

    def delete_student(self, student_id):
        student = next(
            (s for s in self.students if s.student_id == student_id),
            None
        )

        if student is None:
            return "Student not found."

        for book in self.books:
            if not book.available and book.issued_to == student_id:
                return "Cannot delete student. Return their issued book first."

        # A member may be deleted once they have no books currently issued to them.
        # Previous borrowing history does not prevent deletion.

        self.students.remove(student)
        self.save_data()
        return "Student deleted successfully."

    def issue_book(self, book_id, student_id):
        book = next(
            (b for b in self.books if b.book_id == book_id),
            None
        )
        student = next(
            (s for s in self.students if s.student_id == student_id),
            None
        )

        if book is None:
            return "Book not found."

        if student is None:
            return "Student not found."

        if not book.available:
            return "Book is already issued."

        book.available = False
        book.issued_to = student_id
        book.issue_date = date.today().isoformat()
        book.due_date = (date.today() + timedelta(days=14)).isoformat()
        if student_id not in book.issued_student_ids:
            book.issued_student_ids.append(student_id)
        book.issued_count += 1

        self.save_data()
        return "Book issued successfully."

    def delete_book(self, book_id):
        book = next((b for b in self.books if b.book_id == book_id), None)
        if book is None:
            return "Book not found."
        if not book.available:
            return "Cannot delete this book while it is issued. Return it first."
        # Available books can be removed from the catalogue, including books
        # that were issued previously and have since been returned.
        self.books.remove(book)
        self.save_data()
        return "Book deleted successfully."

    def return_book(self, book_id, days):
        book = next(
            (b for b in self.books if b.book_id == book_id),
            None
        )

        if book is None:
            return "Book not found."

        if book.available:
            return "This book has not been issued."

        charge = max(0, days - 14) * 5
        due_date = book.due_date
        # Older saved records may not have a due date; derive one from issue date when possible.
        if not due_date and book.issue_date:
            try:
                due_date = (date.fromisoformat(book.issue_date) + timedelta(days=14)).isoformat()
            except ValueError:
                due_date = "Not recorded"
        if not due_date:
            due_date = "Not recorded"

        book.available = True
        book.issued_to = ""
        book.issue_date = ""
        book.due_date = ""
        self.save_data()

        return {"message": f"Book returned successfully. Late fee: ₹{charge}.", "late": charge > 0, "late_fee": charge, "due_date": due_date}


# -------------------- LIBRARY OBJECT --------------------

library = Library()


def wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def form_response(message, success=False, **extra):
    if wants_json():
        return jsonify({"message": message, "success": success, **extra}), (200 if success else 400)
    return redirect(url_for("index", message=message))


def valid_book_id(value):
    """Book IDs must contain digits only."""
    return bool(re.fullmatch(r"[0-9]{1,30}", value or ""))


def valid_student_id(value):
    """Student IDs must be alphanumeric, with no spaces or symbols."""
    return bool(re.fullmatch(r"[A-Za-z0-9]{1,30}", value or ""))


def valid_person_name(value, maximum=80):
    """Names may contain letters, spaces and common name punctuation, never digits."""
    value = value or ""
    return (
        bool(value)
        and len(value) <= maximum
        and any(ch.isalpha() for ch in value)
        and all(ch.isalpha() or ch.isspace() or ch in " .'-’" for ch in value)
    )


def valid_book_title(value):
    """Book titles are alphabetic; spaces and common punctuation are allowed."""
    value = value or ""
    return (
        bool(value)
        and len(value) <= 150
        and any(ch.isalpha() for ch in value)
        and all(ch.isalpha() or ch.isspace() or ch in " .,'’:-" for ch in value)
    )


# -------------------- HOME PAGE --------------------

@app.route("/")
def index():
    total_books = len(library.books)
    available = sum(1 for book in library.books if book.available)
    issued = total_books - available

    return render_template(
        "index.html",
        books=library.books,
        students=library.students,
        total_books=total_books,
        available=available,
        issued=issued,
        message=request.args.get("message", ""),
        chart_available=available,
        chart_issued=issued
    )


# -------------------- ADD BOOK --------------------

@app.route("/add_book", methods=["POST"])
def add_book():
    book_id = request.form.get("book_id", "").strip()
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    if not valid_book_id(book_id):
        return form_response("Book ID must contain numbers only (up to 30 digits).")
    if not valid_book_title(title):
        return form_response("Book name must contain letters only; numbers are not allowed.")
    if not valid_person_name(author):
        return form_response("Author name must contain letters only; numbers are not allowed.")
    message = library.add_book(book_id, title, author)
    return form_response(message, message == "Book added successfully.")


# -------------------- ADD STUDENT --------------------

@app.route("/add_student", methods=["POST"])
def add_student():
    student_id = request.form.get("student_id", "").strip()
    name = request.form.get("name", "").strip()
    if not valid_student_id(student_id):
        return form_response("Student ID must contain letters and numbers only, with no spaces or symbols.")
    if not valid_person_name(name):
        return form_response("Enter a valid student name (letters, spaces, apostrophes, periods or hyphens).")
    message = library.add_student(student_id, name)
    return form_response(message, message == "Student added successfully.")


# -------------------- DELETE STUDENT --------------------

@app.route("/delete_book/<book_id>", methods=["POST"])
def delete_book(book_id):
    message = library.delete_book(book_id)
    return form_response(message, message == "Book deleted successfully.")


@app.route("/delete_student/<student_id>", methods=["POST"])
def delete_student(student_id):
    message = library.delete_student(student_id)
    return form_response(message, message == "Student deleted successfully.")


# -------------------- ISSUE BOOK --------------------

@app.route("/issue_book", methods=["POST"])
def issue_book():
    book_id = request.form.get("book_id", "").strip()
    student_id = request.form.get("student_id", "").strip()
    if not valid_book_id(book_id):
        return form_response("Book ID must contain numbers only.")
    if not valid_student_id(student_id):
        return form_response("Student ID must contain letters and numbers only, with no spaces or symbols.")
    message = library.issue_book(book_id, student_id)
    return form_response(message, message == "Book issued successfully.")


# -------------------- RETURN BOOK --------------------

@app.route("/return_book", methods=["POST"])
def return_book():
    book_id = request.form.get("book_id", "").strip()
    days_text = request.form.get("days", "").strip()
    if not valid_book_id(book_id):
        return form_response("Book ID must contain numbers only.")
    if not days_text.isdigit():
        return form_response("Days borrowed must be a whole number greater than or equal to 0.")
    days = int(days_text)
    if days > 36500:
        return form_response("Days borrowed cannot exceed 36,500.")
    result = library.return_book(book_id, days)
    if isinstance(result, str):
        return form_response(result, False)
    return form_response(result["message"], True, late=result["late"], late_fee=result["late_fee"], due_date=result["due_date"])


# -------------------- RUN APPLICATION --------------------

if __name__ == "__main__":
    app.run(debug=True)