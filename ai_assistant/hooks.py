app_name = "ai_assistant"
app_title = "Ai Assistant"
app_publisher = "Glascutr Limited"
app_description = "Ai Assistant that help in my ERPNext as like as me as a logged user."
app_email = "nazmul@glascutr.com"
app_license = "mit"
required_apps = []

after_install = "ai_assistant.install.after_install"
after_migrate = "ai_assistant.install.after_migrate"

has_permission = {
	"AI Conversation": "ai_assistant.permissions.conversation_has_permission",
	"AI Message": "ai_assistant.permissions.message_has_permission",
	"AI Attachment": "ai_assistant.permissions.owned_record_has_permission",
	"AI Action Request": "ai_assistant.permissions.owned_record_has_permission",
	"AI Usage Log": "ai_assistant.permissions.owned_record_has_permission",
}

permission_query_conditions = {
	"AI Conversation": "ai_assistant.permissions.conversation_query",
	"AI Message": "ai_assistant.permissions.message_query",
	"AI Attachment": "ai_assistant.permissions.attachment_query",
	"AI Action Request": "ai_assistant.permissions.action_request_query",
	"AI Usage Log": "ai_assistant.permissions.usage_log_query",
}

scheduler_events = {
	"hourly": ["ai_assistant.tasks.expire_action_requests"],
}

app_include_js = "ai_assistant.bundle.js"
app_include_css = "ai_assistant.bundle.css"
