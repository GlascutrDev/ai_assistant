"""Raw tables that DocType JSON cannot declare (SPEC §4.13). Run from after_migrate only: DDL commits."""

import frappe

CHECKPOINT_DDL = (
	"""CREATE TABLE IF NOT EXISTS `ai_checkpoint` (
		`thread_id` VARCHAR(140) NOT NULL,
		`checkpoint_ns` VARCHAR(100) NOT NULL DEFAULT '',
		`checkpoint_id` VARCHAR(64) NOT NULL,
		`parent_checkpoint_id` VARCHAR(64) NULL,
		`type` VARCHAR(32) NULL,
		`checkpoint` LONGBLOB NOT NULL,
		`metadata` LONGBLOB NOT NULL,
		`created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
		PRIMARY KEY (`thread_id`, `checkpoint_ns`, `checkpoint_id`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
	"""CREATE TABLE IF NOT EXISTS `ai_checkpoint_blob` (
		`thread_id` VARCHAR(140) NOT NULL,
		`checkpoint_ns` VARCHAR(100) NOT NULL DEFAULT '',
		`channel` VARCHAR(150) NOT NULL,
		`version` VARCHAR(100) NOT NULL,
		`type` VARCHAR(32) NOT NULL,
		`blob` LONGBLOB NULL,
		PRIMARY KEY (`thread_id`, `checkpoint_ns`, `channel`, `version`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
	"""CREATE TABLE IF NOT EXISTS `ai_checkpoint_write` (
		`thread_id` VARCHAR(140) NOT NULL,
		`checkpoint_ns` VARCHAR(100) NOT NULL DEFAULT '',
		`checkpoint_id` VARCHAR(64) NOT NULL,
		`task_id` VARCHAR(64) NOT NULL,
		`idx` INT NOT NULL,
		`channel` VARCHAR(150) NOT NULL,
		`type` VARCHAR(32) NULL,
		`blob` LONGBLOB NOT NULL,
		`task_path` VARCHAR(255) NOT NULL DEFAULT '',
		PRIMARY KEY (`thread_id`, `checkpoint_ns`, `checkpoint_id`, `task_id`, `idx`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
)

EMBEDDING_TABLE = "ai_embedding"


def ensure_tables():
	for ddl in CHECKPOINT_DDL:
		frappe.db.sql_ddl(ddl)
	dim = embedding_dimensions()
	if dim and not table_exists(EMBEDDING_TABLE):
		create_embedding_table(dim)


def embedding_dimensions() -> int | None:
	from ai_assistant.services import settings

	profile = settings.find_profile(settings.get().embedding_model)
	return int(profile.dimensions) if profile and profile.dimensions else None


def table_exists(name: str) -> bool:
	return bool(frappe.db.sql("SHOW TABLES LIKE %s", name))


def create_embedding_table(dim: int, drop: bool = False):
	dim = int(dim)
	if drop:
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{EMBEDDING_TABLE}`")
	frappe.db.sql_ddl(
		f"""CREATE TABLE IF NOT EXISTS `{EMBEDDING_TABLE}` (
			`id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
			`source_doctype` VARCHAR(140) NOT NULL,
			`source_name` VARCHAR(140) NOT NULL,
			`conversation` VARCHAR(140) NULL,
			`chunk_no` INT NOT NULL,
			`content` MEDIUMTEXT NOT NULL,
			`metadata` JSON NULL,
			`embedding` VECTOR({dim}) NOT NULL,
			KEY `source` (`source_doctype`, `source_name`),
			KEY `conversation` (`conversation`),
			VECTOR INDEX (`embedding`) M=16 DISTANCE=cosine
		) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
	)


def embedding_table_dimensions() -> int | None:
	if not table_exists(EMBEDDING_TABLE):
		return None
	row = frappe.db.sql(f"SHOW COLUMNS FROM `{EMBEDDING_TABLE}` LIKE 'embedding'", as_dict=True)
	if not row:
		return None
	col_type = row[0]["Type"]
	return int(col_type[col_type.index("(") + 1 : col_type.index(")")])
