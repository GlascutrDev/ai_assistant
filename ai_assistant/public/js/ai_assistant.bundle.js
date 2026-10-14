import { api } from "./chat/api";
import { ChatDrawer } from "./chat/drawer";
import { FilesExtension } from "./chat/files";
import { ChatPanel } from "./chat/panel";
import { VoiceExtension } from "./chat/voice";

frappe.provide("ai_assistant");
ai_assistant.ChatPanel = ChatPanel;
ai_assistant.api = api;
ai_assistant.extensions = [() => new FilesExtension(), () => new VoiceExtension()];

$(document).on("app_ready", async () => {
	if (frappe.session.user === "Guest") return;
	const boot = await api.bootstrap().catch(() => ({ enabled: false }));
	ai_assistant.boot = boot;
	if (!boot.enabled) return;
	ai_assistant.drawer = new ChatDrawer(boot);
	ai_assistant.extensions.forEach((make) => ai_assistant.drawer.panel.extend(make()));
});
