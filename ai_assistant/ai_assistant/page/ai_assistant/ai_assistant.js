frappe.pages["ai-assistant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("AI Assistant"), single_column: true });
	wrapper.ai_page = new AssistantPage(page);
};

frappe.pages["ai-assistant"].on_page_show = function (wrapper) {
	const conversation = frappe.get_route()[1];
	wrapper.ai_page?.ready.then(() => wrapper.ai_page.open(conversation));
};

class AssistantPage {
	constructor(page) {
		this.page = page;
		this.ready = this.make();
	}

	async make() {
		const boot = ai_assistant.boot || (await ai_assistant.api.bootstrap());
		if (!boot.enabled) {
			const $note = $(`<div class="text-muted text-center p-5"></div>`)
				.text(boot.reason || __("The AI Assistant is not available for you."))
				.appendTo(this.page.body);
			if (boot.is_admin) {
				$(`<div class="mt-3"><button class="btn btn-sm btn-primary"></button></div>`)
					.find("button")
					.text(__("Open AI Assistant Settings"))
					.on("click", () => frappe.set_route("Form", "AI Assistant Settings"))
					.end()
					.appendTo($note);
			}
			return;
		}
		this.page.set_title(boot.assistant_name);
		this.page.set_primary_action(__("New Chat"), () => frappe.set_route("ai-assistant"), "add");
		this.$layout = $(`<div class="ai-page"><div class="ai-sidebar"></div><div class="ai-main flex-grow-1"></div></div>`);
		$(this.page.body).append(this.$layout);
		this.$sidebar = this.$layout.find(".ai-sidebar");
		this.panel = new ai_assistant.ChatPanel({
			parent: this.$layout.find(".ai-main"),
			boot,
			on_conversation: (c) => {
				if (frappe.get_route()[1] !== c.name) frappe.router.push_state(`/desk/ai-assistant/${encodeURIComponent(c.name)}`);
				this.refresh_list(c.name);
			},
		});
		ai_assistant.extensions.forEach((make) => this.panel.extend(make()));
	}

	open(conversation) {
		if (!this.panel) return;
		if (conversation && conversation !== this.panel.conversation) this.panel.load(conversation);
		if (!conversation) this.panel.new_chat();
		this.refresh_list(conversation);
	}

	async refresh_list(active) {
		const rows = await ai_assistant.api.list(50);
		this.$sidebar.empty();
		if (!rows.length) this.$sidebar.append($(`<div class="text-muted small p-2"></div>`).text(__("No conversations yet")));
		rows.forEach((row) => {
			$(`<a class="ai-conv ellipsis"></a>`)
				.text(row.title || __("Untitled"))
				.toggleClass("active", row.name === active)
				.on("click", () => frappe.set_route("ai-assistant", row.name))
				.appendTo(this.$sidebar);
		});
	}
}
