"""Curriculum import from a CSV: one row per learning outcome, as in the KICD designs.

Columns: grade, learning_area, strand, sub_strand, outcome. Optional: competency, and scope
(the topics KICD lists for the sub-strand, separated by semicolons).
Importing the same file again adds nothing, so a school can extend a file and re-import it.
A template is in cbc_ai_tutor/setup/curriculum_template.csv.
"""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import cstr, escape_html

REQUIRED = ("grade", "learning_area", "strand", "sub_strand")
BUNDLED = Path(__file__).parent / "curriculum"


class Importer:
	def __init__(self):
		self.created = {"Course": 0, "Strand": 0, "Sub-strand": 0, "Learning Outcome": 0}
		self.order = {}
		self.seen = {}

	def run(self, rows: list[dict]) -> dict:
		for number, row in enumerate(rows, start=2):
			row = {k.strip().lower(): cstr(v).strip() for k, v in row.items() if k}
			missing = [c for c in REQUIRED if not row.get(c)]
			if missing:
				frappe.throw(_("Row {0} has no {1}.").format(number, ", ".join(missing)))
			self.add(row)
		return self.created

	def add(self, row: dict) -> None:
		course = self.course(row["grade"], row["learning_area"])
		strand = self.strand(course, row["strand"][:140])
		sub = self.sub_strand(strand, row["sub_strand"][:140], row.get("scope"))
		if row.get("outcome"):
			self.outcome(sub, row["outcome"], row.get("competency"))

	def next_order(self, parent: str) -> int:
		self.order[parent] = self.order.get(parent, 0) + 1
		return self.order[parent]

	def position(self, parent: str, title: str) -> int:
		"""Order of a title under its parent: where it first appears in the file."""
		if (parent, title) not in self.seen:
			self.seen[(parent, title)] = self.next_order(parent)
		return self.seen[(parent, title)]

	def course(self, grade: str, area: str) -> str:
		if not frappe.db.exists("Program", grade):
			frappe.throw(_("Grade {0} does not exist. Use names like 'Grade 4' or 'PP1'.").format(grade))
		name = f"{grade} {area}"
		if not frappe.db.exists("Course", name):
			frappe.get_doc({"doctype": "Course", "course_name": name}).insert(ignore_permissions=True)
			self.created["Course"] += 1
		if not frappe.db.exists("Program Course", {"parent": grade, "course": name}):
			program = frappe.get_doc("Program", grade)
			program.append("courses", {"course": name, "course_name": name, "required": 1})
			program.save(ignore_permissions=True)
		return name

	def strand(self, course: str, title: str) -> str:
		order = self.position(course, title)
		name = frappe.db.get_value("Strand", {"subject": course, "strand_name": title})
		if name:
			return name
		self.created["Strand"] += 1
		return self.insert("Strand", strand_name=title, subject=course, order=order, active=1)

	def sub_strand(self, strand: str, title: str, scope: str | None) -> str:
		order = self.position(strand, title)
		name = frappe.db.get_value("Sub-strand", {"strand": strand, "name1": title})
		if name:
			return name
		self.created["Sub-strand"] += 1
		return self.insert(
			"Sub-strand", name1=title, strand=strand, order=order, active=1, description=scope_html(scope)
		)

	def outcome(self, sub: str, text: str, competency: str | None) -> None:
		order = self.next_order(sub)
		if frappe.db.exists("Learning Outcome", {"sub_strand": sub, "description": text}):
			return
		self.created["Learning Outcome"] += 1
		self.insert(
			"Learning Outcome", sub_strand=sub, description=text, competency_area=competency, order=order
		)

	@staticmethod
	def insert(doctype: str, **fields) -> str:
		return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True).name


def scope_html(scope: str | None) -> str | None:
	topics = [t.strip() for t in cstr(scope).split(";") if t.strip()]
	if not topics:
		return None
	return "<ul>" + "".join(f"<li>{escape_html(t)}</li>" for t in topics) + "</ul>"


def import_text(text: str) -> dict:
	return Importer().run(list(csv.DictReader(io.StringIO(text.lstrip("﻿")))))


@frappe.whitelist(methods=["POST"])
def import_file(file_url: str) -> dict:
	"""Desk: Strand list → Import curriculum."""
	frappe.only_for(("System Manager", "Academics User"))
	file = frappe.get_doc("File", {"file_url": file_url})
	content = file.get_content()
	return import_text(content.decode("utf-8") if isinstance(content, bytes) else content)


def import_bundled() -> None:
	"""The KICD designs shipped with the app, imported again only when the files change."""
	files = sorted(BUNDLED.glob("*.csv"))
	version = hashlib.sha1(b"".join(f.read_bytes() for f in files)).hexdigest()
	if frappe.db.get_default("cbc_curriculum_version") == version:
		return
	for file in files:
		import_text(file.read_text(encoding="utf-8"))
	frappe.db.set_default("cbc_curriculum_version", version)
