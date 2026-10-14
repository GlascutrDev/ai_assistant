import { api } from "./api";

export class FilesExtension {
	mount(panel) {
		this.panel = panel;
		this.items = [];
		if (!panel.boot.attachments_enabled) return;
		this.$input = $(`<input type="file" multiple class="hidden">`)
			.attr("accept", panel.boot.allowed_file_types.map((t) => "." + t).join(","))
			.appendTo(panel.$wrapper)
			.on("change", (e) => {
				[...e.target.files].forEach((f) => this.add(f));
				e.target.value = "";
			});
		$(`<button class="btn btn-sm btn-default ai-attach"></button>`)
			.attr("title", __("Attach files"))
			.append(frappe.utils.icon("attachment", "sm"))
			.appendTo(panel.$wrapper.find(".ai-tools-left"))
			.on("click", () => this.$input.trigger("click"));
		panel.$wrapper.on("dragover", (e) => e.preventDefault());
		panel.$wrapper.on("drop", (e) => {
			e.preventDefault();
			[...(e.originalEvent.dataTransfer?.files || [])].forEach((f) => this.add(f));
		});
		panel.$input.on("paste", (e) => {
			const pasted = [...(e.originalEvent.clipboardData?.files || [])];
			if (pasted.length) {
				e.preventDefault();
				pasted.forEach((f) => this.add(f));
			}
		});
	}

	async add(file) {
		const boot = this.panel.boot;
		if (this.items.length >= boot.max_files_per_message) {
			frappe.show_alert({ message: __("Too many files for one message."), indicator: "orange" });
			return;
		}
		if (file.size > boot.max_file_size_mb * 1024 * 1024) {
			frappe.show_alert({ message: __("File too large: {0}", [file.name]), indicator: "orange" });
			return;
		}
		const item = { file_name: file.name, status: "Uploading" };
		this.items.push(item);
		this.render();
		try {
			const r = await api.upload(this.panel.conversation, file);
			Object.assign(item, { name: r.attachment, status: r.status });
			if (!this.panel.conversation) {
				this.panel.conversation = r.conversation;
				this.panel.on_conversation?.({ name: r.conversation });
			}
		} catch (e) {
			Object.assign(item, { status: "Failed", error: e.message });
		}
		this.render();
	}

	on_status(data) {
		const item = this.items.find((i) => i.name === data.attachment);
		if (!item) return;
		Object.assign(item, { status: data.status, error: data.error });
		this.render();
	}

	blocks_send() {
		const waiting = this.items.some((i) => !["Ready", "Failed"].includes(i.status));
		if (waiting) frappe.show_alert({ message: __("Wait until the files are ready."), indicator: "orange" });
		return waiting;
	}

	payload() {
		const ready = this.items.filter((i) => i.status === "Ready").map((i) => i.name);
		return ready.length ? { attachments: ready } : {};
	}

	sent() {
		this.items = [];
		this.render();
	}

	reset() {
		this.sent();
	}

	remove(item) {
		this.items = this.items.filter((i) => i !== item);
		if (item.name && item.status !== "Failed") api.remove_attachment(item.name);
		this.render();
	}

	render() {
		const $chips = this.panel.$wrapper.find(".ai-chips").empty();
		this.items.forEach((item) => {
			const $chip = $(`<span class="ai-chip"></span>`).text(item.file_name);
			const state = item.status === "Ready" ? "" : ` · ${__(item.status)}`;
			$chip.append($("<span class='text-muted'></span>").text(state));
			if (item.error) $chip.attr("title", item.error).addClass("text-danger");
			$(`<a href="#" class="text-muted">×</a>`)
				.on("click", (e) => {
					e.preventDefault();
					this.remove(item);
				})
				.appendTo($chip);
			$chips.append($chip);
		});
	}
}
