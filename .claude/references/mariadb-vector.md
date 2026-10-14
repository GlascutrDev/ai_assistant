# MariaDB 11.8 vectors for RAG

Bench MariaDB: `11.8.6`. Checked on `today.localhost` (2026-10-14):
`SELECT VEC_ToText(VEC_FromText('[1,2,3]')), VEC_DISTANCE_COSINE(VEC_FromText('[1,0]'), VEC_FromText('[0,1]'))` → `[1,2,3]`, `1.0`.

## Table (created in `install.after_migrate`)

```sql
CREATE TABLE IF NOT EXISTS `ai_embedding` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- `{dim}` comes from the embedding profile's `dimensions`. A change means `DROP TABLE` + recreate + `rebuild_all` (SPEC §8.4). Validate `dim` as an int before formatting it into DDL.
- A table can hold only one `VECTOR INDEX`, and the indexed column must be `NOT NULL`.

## Insert

```python
frappe.db.sql(
	"""INSERT INTO `ai_embedding`
	(source_doctype, source_name, conversation, chunk_no, content, metadata, embedding)
	VALUES (%s, %s, %s, %s, %s, %s, VEC_FromText(%s))""",
	(dt, dn, conv, i, text, json.dumps(meta), json.dumps(vector)),
)
```

## Search (then filter by permission in Python)

```python
rows = frappe.db.sql(
	"""SELECT source_doctype, source_name, chunk_no, content, metadata,
	          VEC_DISTANCE_COSINE(embedding, VEC_FromText(%s)) AS distance
	   FROM `ai_embedding`
	   WHERE conversation IS NULL
	   ORDER BY distance
	   LIMIT %s""",
	(json.dumps(query_vector), top_k * 4),
	as_dict=True,
)
```

- Use `ORDER BY VEC_DISTANCE_COSINE(...) LIMIT n` so the vector index is used. The function in `ORDER BY` must match the index `DISTANCE`.
- Knowledge search: `conversation IS NULL`. Attachment search: `conversation = %s` (and the conversation already permission-checked).
- Then keep a row only if `frappe.has_permission(source_doctype, "read", source_name)`; for `AI Knowledge Document`, check `visible_to_roles` against `frappe.get_roles()`.
- This is internal SQL on our own table, not on a user-chosen DocType, so it is allowed (`permission-safe-tools.md`). Never format user text into it; always pass parameters.

## Tests
The test site runs the same MariaDB, so vector tests run there. Use a fake embedding model with a small `dimensions` (e.g. 8) and recreate the table in the test's `setUpClass`.
