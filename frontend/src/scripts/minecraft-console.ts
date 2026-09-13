import { getMinecraftConsoleLogs, sendMinecraftCommand } from "../lib/api";
import type { CurrentUser } from "../types/auth";

const CONSOLE_POLL_INTERVAL_MS = 2_000;
const NEAR_BOTTOM_THRESHOLD_PX = 80;

interface MinecraftStatusEventDetail {
	online: boolean;
	reachable: boolean;
}

type ManagementView = "overview" | "console";

const root = document.querySelector<HTMLElement>("[data-minecraft-management]");

if (root) {
	const consoleOutput = root.querySelector<HTMLElement>("[data-console-output]");
	const connection = root.querySelector<HTMLElement>("[data-console-connection]");
	const form = root.querySelector<HTMLFormElement>("[data-console-form]");
	const input = root.querySelector<HTMLInputElement>("[data-console-input]");
	const sendButton = root.querySelector<HTMLButtonElement>("[data-console-send]");
	const feedback = root.querySelector<HTMLElement>("[data-console-feedback]");

	let isAdmin = false;
	let activeView: ManagementView = "overview";
	let serverOnline = false;
	let backendReachable = false;
	let logConnected = false;
	let logAvailable = false;
	let logRequestInFlight = false;
	let commandPending = false;
	let hasReceivedLogs = false;
	let pollTimer: number | null = null;
	let feedbackSource: "logs" | "command" | null = null;
	const commandHistory: string[] = [];
	let historyIndex = 0;
	let historyDraft = "";

	const setFeedback = (
		message: string | null,
		isError = false,
		source: "logs" | "command" = "command",
	): void => {
		if (!feedback) return;
		feedbackSource = message === null ? null : source;
		feedback.hidden = message === null;
		feedback.textContent = message ?? "";
		feedback.classList.toggle("error", isError);
	};

	const renderConnection = (): void => {
		if (!connection) return;
		if (!logConnected) {
			connection.textContent = hasReceivedLogs ? "Disconnected" : "Checking...";
			connection.className = `console-connection ${hasReceivedLogs ? "disconnected" : "checking"}`;
		} else if (!backendReachable || !serverOnline) {
			connection.textContent = "Server Offline";
			connection.className = "console-connection offline";
		} else if (!logAvailable) {
			connection.textContent = "Log Unavailable";
			connection.className = "console-connection unavailable";
		} else {
			connection.textContent = "Connected";
			connection.className = "console-connection connected";
		}
	};

	const renderCommandAvailability = (): void => {
		const disabled = !isAdmin || !serverOnline || !backendReachable || commandPending;
		if (input) {
			input.disabled = disabled;
			input.placeholder = !backendReachable || !serverOnline
				? "Server is offline — commands unavailable"
				: "Enter a Minecraft command";
		}
		if (sendButton) {
			sendButton.disabled = disabled;
			sendButton.textContent = commandPending ? "Sending..." : "Send";
		}
	};

	const shouldPoll = (): boolean =>
		isAdmin && activeView === "console" && document.visibilityState === "visible";

	const clearPollTimer = (): void => {
		if (pollTimer !== null) window.clearTimeout(pollTimer);
		pollTimer = null;
	};

	const schedulePoll = (): void => {
		clearPollTimer();
		if (!shouldPoll()) return;
		pollTimer = window.setTimeout(() => void pollLogs(), CONSOLE_POLL_INTERVAL_MS);
	};

	const pollLogs = async (): Promise<void> => {
		if (!shouldPoll() || logRequestInFlight) return;
		logRequestInFlight = true;

		try {
			const result = await getMinecraftConsoleLogs();
			const hadPreviousResponse = hasReceivedLogs;
			logConnected = true;
			logAvailable = result.available;
			hasReceivedLogs = true;

			if (result.available && consoleOutput) {
				const nearBottom = !consoleOutput.textContent ||
					consoleOutput.scrollHeight - consoleOutput.scrollTop - consoleOutput.clientHeight <
						NEAR_BOTTOM_THRESHOLD_PX;
				consoleOutput.textContent = result.lines.length > 0
					? result.lines.join("\n")
					: "latest.log is empty.";
				if (nearBottom) consoleOutput.scrollTop = consoleOutput.scrollHeight;
			} else if (!result.available && !hadPreviousResponse && consoleOutput) {
				consoleOutput.textContent = result.message ?? "Minecraft latest.log is unavailable.";
			}
			if (!result.available) setFeedback(result.message, false, "logs");
			else if (feedbackSource === "logs") setFeedback(null);
		} catch {
			logConnected = false;
			hasReceivedLogs = true;
			setFeedback(
				"Console logs are temporarily unavailable. Existing output has been preserved.",
				true,
				"logs",
			);
		} finally {
			logRequestInFlight = false;
			renderConnection();
			schedulePoll();
		}
	};

	const selectView = (view: ManagementView): void => {
		if (view === "console" && !isAdmin) return;
		activeView = view;
		for (const tab of root.querySelectorAll<HTMLButtonElement>("[data-view-tab]")) {
			const selected = tab.dataset.viewTab === view;
			tab.classList.toggle("active", selected);
			tab.setAttribute("aria-selected", String(selected));
		}
		for (const panel of root.querySelectorAll<HTMLElement>("[data-view-panel]")) {
			panel.hidden = panel.dataset.viewPanel !== view;
		}

		const nextUrl = new URL(window.location.href);
		nextUrl.hash = view === "console" ? "console" : "";
		window.history.replaceState(null, "", `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
		if (view === "console") {
			clearPollTimer();
			void pollLogs();
			input?.focus();
		} else {
			clearPollTimer();
		}
	};

	for (const tab of root.querySelectorAll<HTMLButtonElement>("[data-view-tab]")) {
		tab.addEventListener("click", () => {
			const view = tab.dataset.viewTab;
			if (view === "overview" || view === "console") selectView(view);
		});
	}

	window.addEventListener("mcpanel:session-ready", (event: Event) => {
		const user = (event as CustomEvent<CurrentUser>).detail;
		isAdmin = user.isAdmin;
		if (isAdmin) {
			for (const element of root.querySelectorAll<HTMLElement>("[data-admin-only]")) {
				element.hidden = false;
			}
			if (window.location.hash === "#console") selectView("console");
		}
		renderCommandAvailability();
	});

	window.addEventListener("mcpanel:minecraft-status", (event: Event) => {
		const status = (event as CustomEvent<MinecraftStatusEventDetail>).detail;
		serverOnline = status.online;
		backendReachable = status.reachable;
		renderConnection();
		renderCommandAvailability();
	});

	document.addEventListener("visibilitychange", () => {
		if (shouldPoll()) {
			clearPollTimer();
			void pollLogs();
		} else {
			clearPollTimer();
		}
	});

	input?.addEventListener("keydown", (event: KeyboardEvent) => {
		if (commandHistory.length === 0 || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
		event.preventDefault();

		if (event.key === "ArrowUp") {
			if (historyIndex === commandHistory.length) historyDraft = input.value;
			historyIndex = Math.max(0, historyIndex - 1);
			input.value = commandHistory[historyIndex] ?? "";
		} else {
			historyIndex = Math.min(commandHistory.length, historyIndex + 1);
			input.value = historyIndex === commandHistory.length
				? historyDraft
				: (commandHistory[historyIndex] ?? "");
		}
		input.setSelectionRange(input.value.length, input.value.length);
	});

	form?.addEventListener("submit", async (event: SubmitEvent) => {
		event.preventDefault();
		if (!input || commandPending || !serverOnline || !backendReachable) return;
		const command = input.value.trim();
		if (!command) {
			setFeedback("Enter a command before sending.", true);
			return;
		}

		commandPending = true;
		setFeedback(null);
		renderCommandAvailability();
		try {
			const result = await sendMinecraftCommand(command);
			commandHistory.push(command);
			historyIndex = commandHistory.length;
			historyDraft = "";
			input.value = "";
			setFeedback(result.response ? `RCON: ${result.response}` : "Command completed.");
			clearPollTimer();
			void pollLogs();
		} catch (error: unknown) {
			const message = error instanceof Error ? error.message : "Unknown request error";
			setFeedback(`Command failed. ${message}`, true);
		} finally {
			commandPending = false;
			renderCommandAvailability();
			input.focus();
		}
	});

	renderConnection();
	renderCommandAvailability();
}
