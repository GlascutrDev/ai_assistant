import { api } from "./api";
import * as render from "./render";

// Frappe's socket gives up after 3 reconnect attempts (e.g. across a bench restart); poll if it goes quiet.
const WATCH_INTERVAL = 4000;

export class ChatPanel {
	constructor({ parent, boot, compact = false, on_conversation = null }) {
		this.boot = boot;
		this.compact = compact;
		this.on_conversation = on_conversation;
		this.conversation = null;
		this.busy = false;
		this.stream_text = "";
		this.extensions = [];
		this.make(parent);
		frappe.realtime.on("ai_assistant_stream", (data) => this.on_event(data));
	}

	make(parent) {
		this.$wrapper = $(`
			<div class="ai-panel ${this.compact ? "ai-compact" : ""}">
				<div class="ai-messages"></div>
				<div class="ai-cards"></div>
				<div class="ai-composer">
					<div class="ai-chips"></div>
					<textarea class="form-control ai-input" rows="2"></textarea>
					<div class="ai-composer-actions">
						<div class="ai-tools-left"></div>
						<button class="btn btn-sm btn-default ai-stop hidden">${__("Stop")}</button>
						<button class="btn btn-sm btn-primary ai-send">${__("Send")}</button>
					</div>
				</div>
			</div>`).appendTo(parent);
		this.$messages = this.$wrapper.find(".ai-messages");
		this.$cards = this.$wrapper.find(".ai-cards");
		this.$input = this.$wrapper.find(".ai-input");
		this.$send = this.$wrapper.find(".ai-send");
		this.$stop = this.$wrapper.find(".ai-stop");
		this.$input.attr("placeholder", __("Ask {0}…", [this.boot.assistant_name]));
		this.$send.on("click", () => this.send());
		this.$stop.on("click", () => this.stop());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
			}
		});
		this.$messages.on("click", "a.ai-desk-link", (e) => {
			e.preventDefault();
			frappe.router.push_state($(e.currentTarget).attr("href"));
		});
		this.show_empty();
	}

	extend(extension) {
		this.extensions.push(extension);
		extension.mount(this);
	}

	show_empty() {
		this.$messages.empty().append(
			$(`<div class="ai-empty text-muted"></div>`).text(
				__("Ask about your data, or ask me to prepare a change. I can only see and do what you can.")
			)
		);
	}

	new_chat() {
		this.conversation = null;
		this.$cards.empty();
		this.show_empty();
		this.set_busy(false);
		this.extensions.forEach((x) => x.reset?.());
		this.$input.trigger("focus");
	}

	async load(conversation) {
		const data = await api.load(conversation);
		this.conversation = conversation;
		this.render_all(data);
		this.on_conversation?.(data.conversation);
	}

	render_all(data) {
		this.$messages.empty();
		data.messages.forEach((m) => this.$messages.append(render.message(m)));
		this.render_cards(data.pending_actions);
		this.set_busy(data.conversation.status === "Running");
		this.scroll();
	}

	render_cards(cards) {
		this.$cards.empty();
		(cards || []).forEach((card) => this.$cards.append(render.action_card(card, this.card_handlers())));
		if ((cards || []).length) this.scroll();
	}

	async send(text_override) {
		const text = (text_override ?? this.$input.val()).trim();
		if (!text || this.busy) return;
		const extra = {};
		for (const x of this.extensions) {
			if (x.blocks_send?.()) return;
			Object.assign(extra, x.payload?.() || {});
		}
		this.set_busy(true);
		this.$messages.find(".ai-empty").remove();
		this.$messages.append(render.message({ role: "user", content: text, input_mode: extra.voice_attachment ? "voice" : "text" }));
		this.$input.val("");
		this.stream_text = "";
		this.show_thinking(true);
		this.early_events = this.conversation ? null : [];
		try {
			const r = await api.send({ text, conversation: this.conversation, context: this.desk_context(), ...extra });
			this.extensions.forEach((x) => x.sent?.());
			if (!this.conversation) {
				this.conversation = r.conversation;
				this.on_conversation?.({ name: r.conversation });
				const early = this.early_events || [];
				this.early_events = null;
				early.forEach((data) => this.on_event(data));
			}
		} catch (e) {
			this.early_events = null;
			this.show_thinking(false);
			this.set_busy(false);
			this.$input.val(text);
			if (this.conversation) this.load(this.conversation);
		}
	}

	show_thinking(on) {
		this.$messages.find(".ai-thinking").remove();
		if (on) {
			this.$messages.append(
				$(`<div class="ai-thinking text-muted small"><span class="ai-dots"></span></div>`).prepend(
					document.createTextNode(__("Thinking"))
				)
			);
			this.scroll();
		}
	}

	async stop() {
		if (this.conversation) await api.cancel(this.conversation);
	}

	on_event(data) {
		if (!data) return;
		if (!this.conversation && this.early_events) {
			this.early_events.push(data);
			return;
		}
		if (data.conversation !== this.conversation) return;
		this.last_event = Date.now();
		if (data.type === "token") {
			this.show_thinking(false);
			this.stream_text += data.text;
			this.streaming_bubble().empty().append(render.markdown(this.stream_text));
		} else if (data.type === "step") {
			this.end_stream_bubble();
			this.$messages.append(render.tool_step(data.tool, null));
			this.show_thinking(true);
		} else if (data.type === "tool_result") {
			this.$messages.find(`.ai-step[data-tool="${CSS.escape(data.tool)}"]`).last().replaceWith(render.tool_step(data.tool, data.status));
		} else if (data.type === "confirmation" || data.type === "done" || data.type === "error") {
			this.stream_text = "";
			this.load(this.conversation);
		} else if (data.type === "attachment_status") {
			this.extensions.forEach((x) => x.on_status?.(data));
		}
		this.scroll();
	}

	end_stream_bubble() {
		this.$messages.find(".ai-streaming").removeClass("ai-streaming");
		this.stream_text = "";
	}

	streaming_bubble() {
		let $bubble = this.$messages.find(".ai-streaming .ai-bubble");
		if (!$bubble.length) {
			$bubble = $(`<div class="ai-bubble"></div>`);
			$(`<div class="ai-msg ai-msg-assistant ai-streaming"></div>`).append($bubble).appendTo(this.$messages);
		}
		return $bubble;
	}

	card_handlers() {
		const decide = (card, decision, extra = {}) =>
			api.decide({ action_request: card.name, decision, ...extra }).then(() => {
				this.$cards.find(`[data-name="${card.name}"]`).remove();
				this.set_busy(true);
			});
		return {
			approve: (card) => decide(card, "approve"),
			reject: (card) =>
				frappe.prompt(
					{ fieldname: "message", fieldtype: "Small Text", label: __("Reason (optional)") },
					({ message }) => decide(card, "reject", { message }),
					__("Reject")
				),
			edit: (card) => {
				const dialog = new frappe.ui.Dialog({
					title: __("Edit before approving"),
					fields: [{ fieldname: "args", fieldtype: "Code", options: "JSON", label: __("Arguments") }],
					primary_action_label: __("Approve with changes"),
					primary_action: ({ args }) => {
						let edited;
						try {
							edited = JSON.parse(args);
						} catch {
							frappe.msgprint(__("The arguments are not valid JSON."));
							return;
						}
						dialog.hide();
						decide(card, "edit", { edited_args: edited });
					},
				});
				dialog.set_value("args", JSON.stringify(JSON.parse(card.proposed_args || "{}"), null, 2));
				dialog.show();
			},
		};
	}

	desk_context() {
		const route = frappe.get_route() || [];
		if (route[0] === "Form" && route[1]) return { doctype: route[1], name: route[2] || null };
		if (route[0] === "List" && route[1]) return { doctype: route[1] };
		return null;
	}

	set_busy(busy) {
		this.busy = busy;
		this.$send.prop("disabled", busy);
		this.$stop.toggleClass("hidden", !busy);
		this.$input.prop("disabled", busy || this.$cards.children().length > 0);
		this.watch(busy);
	}

	watch(on) {
		clearInterval(this.watchdog);
		this.watchdog = null;
		if (!on) return;
		reconnect_socket();
		this.last_event = Date.now();
		this.watchdog = setInterval(() => this.check_turn(), WATCH_INTERVAL);
	}

	async check_turn() {
		reconnect_socket();
		if (!this.conversation || Date.now() - this.last_event < WATCH_INTERVAL) return;
		const data = await api.load(this.conversation).catch(() => null);
		if (data && this.busy && data.conversation.name === this.conversation && data.conversation.status !== "Running") {
			this.stream_text = "";
			this.render_all(data);
		}
	}

	scroll() {
		const el = this.$messages.get(0);
		if (el) el.scrollTop = el.scrollHeight;
	}
}

function reconnect_socket() {
	const socket = frappe.realtime.socket;
	if (socket && !socket.connected && !frappe.realtime.disabled) socket.connect();
}
