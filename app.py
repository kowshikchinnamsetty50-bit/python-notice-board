
from flask import Flask, render_template, request, redirect, url_for, flash, Response
import json
import os
import csv
import io
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "notice-board-organizer-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_NAME = os.path.join(BASE_DIR, "notices.json")

CATEGORIES = ["Academic", "Events", "Exams", "General"]


# ---------------- DATA STORAGE ----------------

def load_notices():
    if not os.path.exists(FILE_NAME):
        return []

    try:
        with open(FILE_NAME, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_notices(notices):
    with open(FILE_NAME, "w", encoding="utf-8") as file:
        json.dump(notices, file, indent=4)


# ---------------- NOTICE STATUS ----------------

def get_status(expiry_date):
    expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    today = date.today()

    if expiry < today:
        return "Expired"
    elif (expiry - today).days <= 3:
        return "Expiring Soon"
    return "Active"


def prepare_notices(notices):
    result = []

    for notice in notices:
        item = notice.copy()

        try:
            item["status"] = get_status(item["expiry_date"])
        except (ValueError, KeyError, TypeError):
            item["status"] = "Invalid Date"

        result.append(item)

    return result


# ---------------- DASHBOARD ----------------

@app.route("/")
def home():
    notices = prepare_notices(load_notices())

    search = request.args.get("search", "").strip().lower()
    category = request.args.get("category", "").strip()

    filtered = notices

    if search:
        filtered = [
            n for n in filtered
            if search in n.get("title", "").lower()
            or search in n.get("description", "").lower()
        ]

    if category in CATEGORIES:
        filtered = [
            n for n in filtered
            if n.get("category") == category
        ]

    total = len(notices)
    active = sum(n["status"] == "Active" for n in notices)
    expired = sum(n["status"] == "Expired" for n in notices)
    soon = sum(n["status"] == "Expiring Soon" for n in notices)

    category_counts = {
        cat: sum(n.get("category") == cat for n in notices)
        for cat in CATEGORIES
    }

    # Average notice duration in days
    durations = []

    for n in notices:
        try:
            created = datetime.strptime(
                n["created_date"], "%Y-%m-%d"
            ).date()

            expiry = datetime.strptime(
                n["expiry_date"], "%Y-%m-%d"
            ).date()

            durations.append((expiry - created).days)
        except (ValueError, KeyError):
            pass

    average_duration = (
        round(sum(durations) / len(durations), 1)
        if durations else 0
    )

    max_category = max(category_counts.values(), default=0)

    return render_template(
        "index.html",
        notices=filtered,
        total=total,
        active=active,
        expired=expired,
        soon=soon,
        category_counts=category_counts,
        average_duration=average_duration,
        max_category=max_category,
        categories=CATEGORIES,
        selected_category=category,
        search=search
    )


# ---------------- ADD NOTICE ----------------

@app.route("/add", methods=["POST"])
def add_notice():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    created = request.form.get("created_date", "").strip()
    expiry = request.form.get("expiry_date", "").strip()

    if not title or not description or not created or not expiry:
        flash("Please complete all required fields.", "error")
        return redirect(url_for("home"))

    if len(title) > 120 or len(description) > 2000:
        flash("Title or description is too long.", "error")
        return redirect(url_for("home"))

    if category not in CATEGORIES:
        flash("Please select a valid category.", "error")
        return redirect(url_for("home"))

    try:
        created_date = datetime.strptime(created, "%Y-%m-%d").date()
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    except ValueError:
        flash("Please enter valid dates.", "error")
        return redirect(url_for("home"))

    if expiry_date < created_date:
        flash("Expiry date cannot be before creation date.", "error")
        return redirect(url_for("home"))

    notices = load_notices()

    notice_id = max(
        [n.get("id", 0) for n in notices if isinstance(n.get("id"), int)],
        default=0
    ) + 1

    notice = {
        "id": notice_id,
        "title": title,
        "category": category,
        "description": description,
        "created_date": created,
        "expiry_date": expiry,
        "status": get_status(expiry)
    }

    notices.append(notice)
    save_notices(notices)

    flash("Notice added successfully!", "success")
    return redirect(url_for("home"))


# ---------------- DELETE NOTICE ----------------

@app.route("/delete/<int:notice_id>", methods=["POST"])
def delete_notice(notice_id):
    notices = load_notices()

    updated = [
        n for n in notices
        if n.get("id") != notice_id
    ]

    if len(updated) == len(notices):
        flash("Notice not found.", "error")
    else:
        save_notices(updated)
        flash("Notice deleted successfully.", "success")

    return redirect(url_for("home"))


# ---------------- CSV IMPORT ----------------

@app.route("/import", methods=["POST"])
def import_csv():
    uploaded = request.files.get("csv_file")

    if not uploaded or not uploaded.filename.lower().endswith(".csv"):
        flash("Please select a valid CSV file.", "error")
        return redirect(url_for("home"))

    try:
        stream = io.StringIO(
            uploaded.stream.read().decode("utf-8-sig")
        )

        reader = csv.DictReader(stream)

        required = {
            "title", "category", "description",
            "created_date", "expiry_date"
        }

        if not reader.fieldnames or not required.issubset(
            set(reader.fieldnames)
        ):
            flash("CSV must contain title, category, description, created_date and expiry_date columns.", "error")
            return redirect(url_for("home"))

        notices = load_notices()
        next_id = max(
            [n.get("id", 0) for n in notices if isinstance(n.get("id"), int)],
            default=0
        ) + 1

        added = 0
        errors = 0

        for row in reader:
            try:
                title = row["title"].strip()
                category = row["category"].strip()
                description = row["description"].strip()
                created = row["created_date"].strip()
                expiry = row["expiry_date"].strip()

                created_date = datetime.strptime(created, "%Y-%m-%d").date()
                expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()

                if not title or category not in CATEGORIES:
                    raise ValueError()

                if expiry_date < created_date:
                    raise ValueError()

                notices.append({
                    "id": next_id,
                    "title": title,
                    "category": category,
                    "description": description,
                    "created_date": created,
                    "expiry_date": expiry,
                    "status": get_status(expiry)
                })

                next_id += 1
                added += 1

            except (ValueError, KeyError, AttributeError):
                errors += 1

        save_notices(notices)

        flash(
            f"Imported {added} notices. Invalid rows skipped: {errors}.",
            "success" if added else "error"
        )

    except (UnicodeDecodeError, OSError, csv.Error):
        flash("Unable to read this CSV file.", "error")

    return redirect(url_for("home"))


# ---------------- REPORT EXPORT ----------------

@app.route("/export/<report_type>")
def export_report(report_type):
    notices = prepare_notices(load_notices())

    if report_type == "csv":
        output = io.StringIO()
        fields = [
            "id", "title", "category", "description",
            "created_date", "expiry_date", "status"
        ]

        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()

        for notice in notices:
            writer.writerow({
                key: notice.get(key, "") for key in fields
            })

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                "attachment; filename=notices_report.csv"
            }
        )

    elif report_type in ("txt", "md"):
        lines = [
            "NOTICE BOARD ORGANIZER REPORT",
            "Generated: " + date.today().isoformat(),
            "=" * 45,
            ""
        ]

        for notice in notices:
            lines.extend([
                "ID: " + str(notice.get("id", "")),
                "Title: " + notice.get("title", ""),
                "Category: " + notice.get("category", ""),
                "Description: " + notice.get("description", ""),
                "Created: " + notice.get("created_date", ""),
                "Expiry: " + notice.get("expiry_date", ""),
                "Status: " + notice.get("status", ""),
                "-" * 45
            ])

        content = "\n".join(lines)
        extension = "txt" if report_type == "txt" else "md"

        return Response(
            content,
            mimetype="text/plain; charset=utf-8",
            headers={
                "Content-Disposition":
                f"attachment; filename=notices_report.{extension}"
            }
        )

    flash("Invalid report format.", "error")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
