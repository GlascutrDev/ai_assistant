import { api } from "./api";

const esc = (text) => frappe.utils.escape_html(text == null ? "" : String(text));

const TOOL_LABELS = {
	find_doctypes: __("Finding record types"),
	describe_doctype: __("Reading fields"),
	list_documents: __("Listing records"),
	count_documents: __("Counting records"),
	aggregate: __("Calculating totals"),
	get_document: __("Opening a record"),
	run_report: __("Running a report"),
	search_links: __("Searching records"),
	search_knowledge: __("Searching the knowledge base"),
	read_attachment: __("Reading a file"),
	search_attachments: __("Searching files"),
	inspect_spreadsheet: __("Reading a spreadsheet"),
	query_spreadsheet: __("Analyzing a spreadsheet"),
};

export function tool_label(name) {
	return TOOL_LABELS[name] || __("Preparing {0}", [name.replace(/_/g, " ")]);
}

export function markdown(text) {
	// frappe.markdown sanitizes its output with an allow-list.
	const safe_html = frappe.markdown(text || "");
	const $el = $(`<div class="ai-md"></div>`).html(safe_html);
	$el.find("a[href^='/desk/'], a[href^='/app/']").removeAttr("target").addClass("ai-desk-link");
	return $el;
}

export function message(m) {
	if (m.role === "tool") return tool_step(m.tool_name, m.tool_status, tool_error(m.content));
	const $row = $(`<div class="ai-msg ai-msg-${esc(m.role)}"></div>`);
	if (m.role === "user") {
		$row.append($(`<div class="ai-bubble"></div>`).text(m.content));
		if (m.input_mode === "voice") $row.find(".ai-bubble").prepend(frappe.utils.icon("mic", "xs"));
	} else if (m.role === "assistant") {
		$row.append($(`<div class="ai-bubble"></div>`).append(markdown(m.content)));
		if (m.name) $row.append(feedback(m));
		if (m.langsmith_run_id) {
			$row.append(`<div class="ai-meta text-muted small">${__("Trace")}: ${esc(m.langsmith_run_id)}</div>`);
		}
	} else {
		$row.append($(`<div class="ai-note text-muted small"></div>`).text(m.content));
	}
	return $row;
}

function feedback(m) {
	const $bar = $(`<div class="ai-feedback text-muted small"></div>`);
	const button = (rating, icon, title) =>
		$(`<button class="btn btn-xs btn-link" aria-label="${esc(title)}" title="${esc(title)}"></button>`)
			.toggleClass("text-primary", m.rating === rating)
			.attr("aria-pressed", m.rating === rating ? "true" : "false")
			.append(frappe.utils.icon(icon, "xs"))
			.on("click", () => rate(m, rating, $bar));
	return $bar.append(button("Up", "thumbs-up", __("Good answer")), button("Down", "thumbs-down", __("Bad answer")));
}

function rate(m, rating, $bar) {
	const send = (comment) =>
		api.rate(m.name, rating, comment).then((r) => {
			m.rating = rating;
			$bar.replaceWith(feedback(m));
			if (r.memory) frappe.show_alert({ message: __("Saved to your memories"), indicator: "green" });
		});
	if (rating === "Up") return send(null);
	frappe.prompt(
		{ fieldname: "comment", fieldtype: "Small Text", label: __("What was wrong? (saved to your memories)") },
		(values) => send(values.comment || null),
		__("Bad answer"),
		__("Send")
	);
}

export function tool_step(name, status, error) {
	const icon = { ok: "check", denied: "lock", error: "close" }[status] || "refresh";
	const $step = $(`<div class="ai-step text-muted small" data-tool="${esc(name)}"></div>`);
	$step.append(frappe.utils.icon(icon, "xs")).append($("<span></span>").text(" " + tool_label(name)));
	if (status === "denied") $step.append($("<span></span>").text(" — " + __("permission denied")));
	if (status === "error" && error) $step.append($(`<span class="text-danger"></span>`).text(" — " + error));
	return $step;
}

function tool_error(content) {
	try {
		const parsed = JSON.parse(content || "{}");
		return parsed && parsed.error ? String(parsed.error).slice(0, 300) : null;
	} catch {
		return null;
	}
}

export function action_card(card, handlers) {
	const target = card.target_doctype
		? `${esc(__(card.target_doctype))}${card.target_name ? " " + esc(card.target_name) : ""}`
		: "";
	const $card = $(`
		<div class="ai-card" data-name="${esc(card.name)}">
			<div class="ai-card-title">${esc(__("Confirm"))}: ${esc(operation_label(card.operation))} ${target}</div>
			<div class="ai-card-diff"></div>
			<div class="ai-card-actions">
				<button class="btn btn-xs btn-primary ai-approve">${esc(__("Approve"))}</button>
				<button class="btn btn-xs btn-default ai-edit">${esc(__("Edit"))}</button>
				<button class="btn btn-xs btn-default ai-reject">${esc(__("Reject"))}</button>
			</div>
		</div>`);
	// diff_html is built on the server from escaped values (tools/preview.py).
	$card.find(".ai-card-diff").html(card.diff_html || "");
	$card.find(".ai-approve").on("click", () => handlers.approve(card));
	$card.find(".ai-edit").on("click", () => handlers.edit(card));
	$card.find(".ai-reject").on("click", () => handlers.reject(card));
	return $card;
}

function operation_label(operation) {
	const labels = {
		create: __("Create"),
		update: __("Update"),
		submit: __("Submit"),
		cancel: __("Cancel"),
		delete: __("Delete"),
		comment: __("Comment on"),
		assign: __("Assign"),
		workflow: __("Workflow action on"),
		attach: __("Attach file to"),
		email: __("Send email"),
	};
	return labels[operation] || operation;
}
