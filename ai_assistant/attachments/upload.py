"""Upload checks (SPEC §6.8, §7.4): extension allow-list, content sniffing, size, image clean-up."""

import io
import os
from dataclasses import dataclass

import filetype
import frappe
from frappe import _

from ai_assistant.attachments.extractors import check_zip, decode_text
from ai_assistant.services import settings

ZIP = "application/zip"
TYPES = {
	"png": ("image", ("image/png",)),
	"jpg": ("image", ("image/jpeg",)),
	"jpeg": ("image", ("image/jpeg",)),
	"webp": ("image", ("image/webp",)),
	"gif": ("image", ("image/gif",)),
	"pdf": ("pdf", ("application/pdf",)),
	"docx": ("document", ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ZIP)),
	"xlsx": ("spreadsheet", ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ZIP)),
	"xlsm": (
		"spreadsheet",
		(
			"application/vnd.ms-excel.sheet.macroenabled.12",
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			ZIP,
		),
	),
	"xls": ("spreadsheet", ("application/vnd.ms-excel",)),
	"csv": ("spreadsheet", ("text/csv",)),
	"tsv": ("spreadsheet", ("text/tab-separated-values",)),
	"txt": ("text", ("text/plain",)),
	"md": ("text", ("text/markdown",)),
	"json": ("text", ("application/json",)),
	"mp3": ("audio", ("audio/mpeg",)),
	"m4a": ("audio", ("audio/mp4", "video/mp4")),
	"mp4": ("audio", ("audio/mp4", "video/mp4")),
	"wav": ("audio", ("audio/x-wav", "audio/wav")),
	"webm": ("audio", ("video/webm", "audio/webm")),
	"ogg": ("audio", ("audio/ogg",)),
}
TEXT_KINDS_BY_EXT = ("csv", "tsv", "txt", "md", "json")
MAX_IMAGE_SIDE = 2048


class UploadRefusedError(frappe.ValidationError):
	pass


@dataclass
class CheckedFile:
	file_name: str
	data: bytes
	kind: str
	mime_type: str


def check(file_name: str, data: bytes, voice: bool = False) -> CheckedFile:
	"""Refuse anything not allowed; return the cleaned bytes with kind and MIME type."""
	conf = settings.get()
	file_name = os.path.basename(file_name or "file").strip() or "file"
	ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
	allowed = settings.allowed_file_types() | ({"webm", "ogg", "mp4", "m4a", "wav"} if voice else set())
	if ext not in allowed or ext not in TYPES:
		_refuse(_("Files of type .{0} are not allowed.").format(ext or "?"))
	limit = (conf.max_file_size_mb or 20) * 1024 * 1024
	if len(data) > limit:
		_refuse(_("File too large. The limit is {0} MB.").format(conf.max_file_size_mb or 20))
	if not data:
		_refuse(_("The file is empty."))
	kind, mimes = TYPES[ext]
	mime = _sniff(ext, data, mimes)
	if kind == "image":
		_require_image_support()
		data = clean_image(data, mime)
	elif ext in ("docx", "xlsx", "xlsm"):
		check_zip(data)
	return CheckedFile(file_name, data, "voice" if voice else kind, mime)


def clean_image(data: bytes, mime: str) -> bytes:
	"""Rotate by EXIF, shrink to 2048 px, and save again without EXIF."""
	from PIL import Image, ImageOps

	try:
		image = Image.open(io.BytesIO(data))
		if getattr(image, "is_animated", False):
			return data
		image = ImageOps.exif_transpose(image)
		image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
		out = io.BytesIO()
		fmt = {"image/png": "PNG", "image/webp": "WEBP", "image/gif": "GIF"}.get(mime, "JPEG")
		if fmt == "JPEG" and image.mode not in ("RGB", "L"):
			image = image.convert("RGB")
		image.save(out, format=fmt)
		return out.getvalue()
	except Exception:
		_refuse(_("The image could not be read."))


def _sniff(ext: str, data: bytes, mimes: tuple[str, ...]) -> str:
	if ext in TEXT_KINDS_BY_EXT:
		if filetype.guess(data) is not None:
			_refuse(_("The file content does not match its name."))
		decode_text(data)
		return mimes[0]
	guess = filetype.guess(data)
	if not guess or guess.mime not in mimes:
		_refuse(_("The file content does not match its name."))
	return mimes[0] if guess.mime == ZIP else guess.mime


def _require_image_support():
	main = settings.find_profile(settings.get().main_model)
	if not main or not main.supports_images:
		_refuse(_("The current model cannot read images."))


def _refuse(message: str):
	frappe.throw(message, UploadRefusedError)
