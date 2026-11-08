import { api } from "./api";

const SILENCE_SECONDS = 3;
const SILENCE_LEVEL = 0.02;

export class VoiceExtension {
	mount(panel) {
		this.panel = panel;
		this.attachment = null;
		if (!panel.boot.voice_enabled || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return;
		this.$button = $(`<button class="btn btn-sm btn-default ai-mic"></button>`)
			.attr("title", __("Speak your question"))
			.append(frappe.utils.icon("mic", "sm"))
			.appendTo(panel.$wrapper.find(".ai-tools-left"))
			.on("click", () => (this.recorder ? this.stop() : this.start()));
		this.$timer = $(`<span class="ai-timer text-muted small hidden"></span>`).insertAfter(this.$button);
		panel.$input.on("input", () => {
			if (!panel.$input.val().trim()) this.attachment = null;
		});
	}

	async start() {
		try {
			this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
		} catch {
			frappe.msgprint(__("The browser did not allow the microphone. HTTPS is needed outside localhost."));
			return;
		}
		const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/mp4";
		this.chunks = [];
		this.started = Date.now();
		this.recorder = new MediaRecorder(this.stream, { mimeType: type });
		this.recorder.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
		this.recorder.onstop = () => this.upload(type);
		this.recorder.start();
		this.$button.addClass("btn-danger");
		this.$timer.removeClass("hidden");
		this.watch_silence();
		this.tick = setInterval(() => this.on_tick(), 250);
	}

	on_tick() {
		const seconds = (Date.now() - this.started) / 1000;
		this.$timer.text(`${Math.floor(seconds)}s / ${this.panel.boot.max_voice_seconds}s`);
		if (seconds >= this.panel.boot.max_voice_seconds) this.stop();
	}

	watch_silence() {
		const context = new AudioContext();
		const analyser = context.createAnalyser();
		context.createMediaStreamSource(this.stream).connect(analyser);
		const samples = new Float32Array(analyser.fftSize);
		let quiet_since = Date.now();
		this.audio_context = context;
		const check = () => {
			if (!this.recorder) return;
			analyser.getFloatTimeDomainData(samples);
			const level = Math.sqrt(samples.reduce((sum, v) => sum + v * v, 0) / samples.length);
			if (level > SILENCE_LEVEL) quiet_since = Date.now();
			if (Date.now() - quiet_since > SILENCE_SECONDS * 1000 && Date.now() - this.started > 1500) this.stop();
			else requestAnimationFrame(check);
		};
		check();
	}

	stop() {
		if (!this.recorder) return;
		this.duration = (Date.now() - this.started) / 1000;
		clearInterval(this.tick);
		this.recorder.stop();
		this.recorder = null;
		this.stream.getTracks().forEach((t) => t.stop());
		this.audio_context?.close();
		this.$button.removeClass("btn-danger");
		this.$timer.text(__("Transcribing…"));
	}

	async upload(type) {
		const ext = type.startsWith("audio/webm") ? "webm" : "mp4";
		const blob = new File(this.chunks, `recording.${ext}`, { type: type.split(";")[0] });
		try {
			const r = await api.upload(this.panel.conversation, blob, "audio", "transcribe", {
				duration_seconds: this.duration.toFixed(1),
				...this.panel.agent_args(),
			});
			if (!this.panel.conversation) {
				this.panel.conversation = r.conversation;
				this.panel.render_agent_bar(this.panel.agent_title());
				this.panel.on_conversation?.({ name: r.conversation });
			}
			this.attachment = r.attachment;
			if (this.panel.boot.voice_auto_send) {
				this.panel.send(r.text);
			} else {
				this.panel.$input.val(r.text).trigger("focus");
			}
		} catch (e) {
			frappe.msgprint(e.message || __("Transcription failed."));
		} finally {
			this.$timer.addClass("hidden");
		}
	}

	payload() {
		return this.attachment ? { voice_attachment: this.attachment } : {};
	}

	sent() {
		this.attachment = null;
	}

	reset() {
		this.attachment = null;
	}
}
