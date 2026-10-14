import frappe

SETTINGS = "AI Assistant Settings"
ASSISTANT_ROLE = "AI Assistant User"
MAX_ROWS_HARD_CAP = 500

DEFAULT_BLOCKED_DOCTYPES = (
	"User",
	"Role",
	"Role Profile",
	"Has Role",
	"User Permission",
	"DocPerm",
	"Custom DocPerm",
	"DocType",
	"Custom Field",
	"Property Setter",
	"Server Script",
	"Client Script",
	"System Settings",
	"Session Default Settings",
	"OAuth Client",
	"Access Log",
	"Activity Log",
	"Error Log",
	"Scheduled Job Type",
)

DEFAULT_FILE_TYPES = "png jpg jpeg webp gif pdf docx xlsx csv txt md json mp3 m4a wav webm ogg"


def get():
	"""The cached Settings document. Do not mutate."""
	return frappe.get_cached_doc(SETTINGS)


def blocked_doctypes() -> set[str]:
	configured = {line.strip() for line in (get().blocked_doctypes or "").splitlines() if line.strip()}
	return set(DEFAULT_BLOCKED_DOCTYPES) | configured


def is_blocked(doctype: str) -> bool:
	return doctype.startswith("AI ") or doctype in blocked_doctypes()


def allowed_file_types() -> set[str]:
	raw = get().allowed_file_types or DEFAULT_FILE_TYPES
	return {ext.strip().lower().lstrip(".") for ext in raw.split() if ext.strip()}


def max_rows() -> int:
	return min(get().max_rows_per_read or 100, MAX_ROWS_HARD_CAP)


def find_profile(profile_id: str | None):
	for row in get().models:
		if row.profile_id == profile_id:
			return row
	return None
