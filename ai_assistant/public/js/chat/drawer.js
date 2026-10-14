import { api } from "./api";
import { ChatPanel } from "./panel";

export class ChatDrawer {
	constructor(boot) {
		this.boot = boot;
		this.$launcher = $(`<button class="ai-launcher btn btn-primary" title="${frappe.utils.escape_html(boot.assistant_name)}"></button>`)
			.append(frappe.utils.icon("assign", "md"))
			.appendTo(document.body)
			.on("click", () => this.toggle());
		this.$drawer = $(`
			<div class="ai-drawer hidden">
				<div class="ai-drawer-header">
					<div class="ai-title ellipsis"></div>
					<div class="ai-header-actions">
						<div class="dropdown">
							<button class="btn btn-xs btn-default dropdown-toggle ai-history" data-toggle="dropdown"></button>
							<ul class="dropdown-menu dropdown-menu-right ai-history-list"></ul>
						</div>
						<button class="btn btn-xs btn-default ai-new"></button>
						<button class="btn btn-xs btn-default ai-expand"></button>
						<button class="btn btn-xs btn-default ai-close"></button>
					</div>
				</div>
				<div class="ai-drawer-body"></div>
			</div>`).appendTo(document.body);
		this.$title = this.$drawer.find(".ai-title").text(boot.assistant_name);
		this.$drawer.find(".ai-history").append(frappe.utils.icon("list", "sm")).attr("title", __("History"));
		this.$drawer.find(".ai-new").append(frappe.utils.icon("add", "sm")).attr("title", __("New chat"));
		this.$drawer.find(".ai-expand").append(frappe.utils.icon("expand", "sm")).attr("title", __("Open full page"));
		this.$drawer.find(".ai-close").append(frappe.utils.icon("close", "sm")).attr("title", __("Close"));
		this.panel = new ChatPanel({
			parent: this.$drawer.find(".ai-drawer-body"),
			boot,
			compact: true,
			on_conversation: (c) => this.$title.text(c.title || boot.assistant_name),
		});
		this.$drawer.find(".ai-new").on("click", () => {
			this.panel.new_chat();
			this.$title.text(boot.assistant_name);
		});
		this.$drawer.find(".ai-close").on("click", () => this.toggle(false));
		this.$drawer.find(".ai-expand").on("click", () => {
			this.toggle(false);
			frappe.set_route("ai-assistant", this.panel.conversation || undefined);
		});
		this.$drawer.find(".ai-history").on("click", () => this.load_history());
		frappe.ui.keys.add_shortcut({
			shortcut: "ctrl+i",
			action: () => this.toggle(),
			description: __("Open {0}", [boot.assistant_name]),
		});
	}

	toggle(show) {
		const open = show ?? this.$drawer.hasClass("hidden");
		this.$drawer.toggleClass("hidden", !open);
		this.$launcher.toggleClass("hidden", open);
		if (open) this.panel.$input.trigger("focus");
	}

	async load_history() {
		const $list = this.$drawer.find(".ai-history-list").empty();
		const rows = await api.list(20);
		if (!rows.length) $list.append($(`<li class="dropdown-item text-muted"></li>`).text(__("No conversations yet")));
		rows.forEach((row) => {
			$(`<li><a class="dropdown-item ellipsis" href="#"></a></li>`)
				.find("a")
				.text(row.title || __("Untitled"))
				.on("click", (e) => {
					e.preventDefault();
					this.panel.load(row.name);
				})
				.end()
				.appendTo($list);
		});
	}
}
