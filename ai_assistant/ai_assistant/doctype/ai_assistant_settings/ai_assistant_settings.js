// Copyright (c) 2026, Glascutr Limited and contributors
// For license information, please see license.txt

const MODEL_PICKERS = {
	main_model: "Chat",
	evaluation_model: "Chat",
	embedding_model: "Embedding",
	speech_model: "Speech-to-text",
};

frappe.ui.form.on("AI Assistant Settings", {
	refresh(frm) {
		set_model_options(frm);
		frm.add_custom_button(__("Test Connection"), () => test_connection(frm), __("Actions"));
		frm.add_custom_button(__("Run Evaluation"), () => run_evaluation(frm), __("Actions"));
		frm.add_custom_button(__("Rebuild Knowledge Index"), () => rebuild_index(frm), __("Actions"));
		if (frm.doc.index_stale) {
			frm.dashboard.set_headline(
				__("The knowledge index is stale. Rebuild it to turn search back on."),
				"orange"
			);
		}
	},
	models_on_form_rendered(frm) {
		set_model_options(frm);
	},
});

frappe.ui.form.on("AI Model Profile", {
	profile_id: set_model_options,
	model_type: set_model_options,
	models_remove: set_model_options,
});

function set_model_options(frm) {
	frm = frm.doc ? frm : cur_frm;
	for (const [fieldname, type] of Object.entries(MODEL_PICKERS)) {
		const options = (frm.doc.models || [])
			.filter((row) => row.model_type === type && row.profile_id)
			.map((row) => row.profile_id);
		frm.set_df_property(fieldname, "options", options);
	}
}

function ensure_saved(frm) {
	if (!frm.is_dirty()) return Promise.resolve();
	return frm.save();
}

function test_connection(frm) {
	const labels = (frm.doc.providers || []).map((row) => row.label).filter(Boolean);
	if (!labels.length) {
		frappe.msgprint(__("Add a provider row first."));
		return;
	}
	frappe.prompt(
		{ fieldname: "label", fieldtype: "Select", label: __("Provider"), options: labels, reqd: 1 },
		({ label }) =>
			ensure_saved(frm).then(() =>
				frappe
					.xcall("ai_assistant.api.settings.test_provider", { label })
					.then((r) => show_test_result(label, r))
			),
		__("Test Connection")
	);
}

function show_test_result(label, r) {
	const title = r.ok ? __("Connected") : __("Connection failed");
	const body = r.ok
		? __("{0} answered with profile {1}: {2}", [label, r.profile, r.detail])
		: r.error;
	frappe.msgprint({ title, message: frappe.utils.escape_html(body), indicator: r.ok ? "green" : "red" });
}

function run_evaluation(frm) {
	frappe.prompt(
		{
			fieldname: "target_model",
			fieldtype: "Autocomplete",
			label: __("Target Model"),
			options: (frm.doc.models || [])
				.filter((row) => row.model_type === "Chat")
				.map((row) => row.profile_id),
			default: frm.doc.main_model,
		},
		({ target_model }) =>
			frappe
				.xcall("ai_assistant.api.settings.run_evaluation", { target_model })
				.then((name) => frappe.set_route("Form", "AI Evaluation Run", name)),
		__("Run Evaluation")
	);
}

function rebuild_index() {
	frappe
		.xcall("ai_assistant.api.settings.rebuild_index")
		.then(() => frappe.show_alert({ message: __("Rebuild queued"), indicator: "blue" }));
}
