const CHAT = "ai_assistant.api.chat.";

const get = (method, args = {}) => frappe.xcall(CHAT + method, args, "GET");
const post = (method, args = {}) => frappe.xcall(CHAT + method, args, "POST");

export const api = {
	bootstrap: () => get("get_bootstrap"),
	list: (limit = 30) => get("list_conversations", { limit }),
	load: (conversation) => get("get_conversation", { conversation }),
	send: (args) => post("send_message", args),
	decide: (args) => post("decide_action", args),
	cancel: (conversation) => post("cancel_turn", { conversation }),
	archive: (conversation) => post("archive_conversation", { conversation }),
	remove_attachment: (attachment) => post("remove_attachment", { attachment }),
	upload(conversation, file, field = "file", method = "upload_attachment", extra = {}) {
		const form = new FormData();
		form.append(field, file, file.name || "recording.webm");
		if (conversation) form.append("conversation", conversation);
		Object.entries(extra).forEach(([key, value]) => form.append(key, value));
		return fetch(`/api/method/${CHAT}${method}`, {
			method: "POST",
			headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
			body: form,
		}).then(async (r) => {
			const body = await r.json().catch(() => ({}));
			if (!r.ok) throw new Error(server_error(body) || __("Upload failed"));
			return body.message;
		});
	},
};

function server_error(body) {
	try {
		const messages = JSON.parse(body._server_messages || "[]");
		return messages.map((m) => JSON.parse(m).message).join("\n");
	} catch {
		return body.exception || body.message;
	}
}
