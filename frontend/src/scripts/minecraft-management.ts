import {
	getMinecraftStatus,
	restartMinecraftServer,
	startMinecraftServer,
	stopMinecraftServer,
} from "../lib/api";
import {
	createUnavailableMinecraftServer,
	minecraftStatusToGameServer,
} from "../lib/minecraft";
import { getServerDisplayValues } from "../lib/server-format";
import type { MinecraftAction } from "../types/api";
import type { GameServer, ServerLifecycleState } from "../types/server";

const POLL_INTERVAL_MS = 5_000;
const OPERATION_TIMEOUTS_MS = {
	start: 120_000,
	stop: 90_000,
	restart: 120_000,
} as const;

type OperationState = Extract<
	ServerLifecycleState,
	"starting" | "stopping" | "restarting"
>;

interface ActiveOperation {
	action: MinecraftAction;
	state: OperationState;
	deadline: number;
	actionAccepted: boolean;
	restartObservedOffline: boolean;
}

type ErrorKind = "connection" | "operation";

const root = document.querySelector<HTMLElement>("[data-minecraft-management]");

if (root) {
	const statusElement = root.querySelector<HTMLElement>("[data-lifecycle-status]");
	const playerListElement = root.querySelector<HTMLElement>("[data-player-list]");
	const normalControls = root.querySelector<HTMLElement>("[data-normal-controls]");
	const operationStateElement = root.querySelector<HTMLElement>("[data-operation-state]");
	const operationLabel = root.querySelector<HTMLElement>("[data-operation-label]");
	const operationMessage = root.querySelector<HTMLElement>("[data-operation-message]");
	const controlError = root.querySelector<HTMLElement>("[data-control-error]");
	const errorMessageElement = root.querySelector<HTMLElement>("[data-error-message]");

	let lifecycle: ServerLifecycleState = "error";
	let server: GameServer = createUnavailableMinecraftServer();
	let backendReachable = false;
	let requestInFlight = false;
	let operation: ActiveOperation | null = null;
	let errorMessage: string | null = null;
	let errorKind: ErrorKind | null = null;

	const setMetricValue = (
		metric: "players" | "uptime" | "memory" | "cpu",
		value: string,
	): void => {
		const element = root.querySelector<HTMLElement>(`[data-metric="${metric}"] strong`);
		if (element) element.textContent = value;
	};

	const renderPlayers = (): void => {
		if (!playerListElement) return;

		if (!backendReachable) {
			const message = document.createElement("p");
			message.textContent = "Player information is unavailable while the backend cannot be reached.";
			playerListElement.replaceChildren(message);
			return;
		}

		if (!server.online) {
			const message = document.createElement("p");
			message.textContent = "The Minecraft server is offline.";
			playerListElement.replaceChildren(message);
			return;
		}

		if (server.players.names.length === 0) {
			const message = document.createElement("p");
			message.textContent = "No players online";
			playerListElement.replaceChildren(message);
			return;
		}

		const list = document.createElement("ul");
		for (const player of server.players.names) {
			const item = document.createElement("li");
			const avatar = document.createElement("span");
			avatar.setAttribute("aria-hidden", "true");
			avatar.textContent = player.charAt(0).toUpperCase();
			item.append(avatar, player);
			list.append(item);
		}
		playerListElement.replaceChildren(list);
	};

	const renderStatus = (): void => {
		if (!statusElement) return;

		const displayState = !backendReachable && !operation ? "unavailable" : lifecycle;
		const label = displayState === "unavailable"
			? "Unavailable"
			: `${displayState.toUpperCase()}${operation ? "..." : ""}`;
		const dot = document.createElement("span");
		dot.setAttribute("aria-hidden", "true");
		statusElement.className = `lifecycle-status ${displayState}`;
		statusElement.replaceChildren(dot, label);
	};

	const renderControls = (): void => {
		const isOperating = operation !== null;
		if (operationStateElement) operationStateElement.hidden = !isOperating;
		if (normalControls) normalControls.hidden = isOperating || !backendReachable;

		const startButton = root.querySelector<HTMLButtonElement>('[data-action="start"]');
		const stopButton = root.querySelector<HTMLButtonElement>('[data-open-confirmation="stop"]');
		const restartButton = root.querySelector<HTMLButtonElement>('[data-open-confirmation="restart"]');
		if (startButton) startButton.hidden = server.online;
		if (stopButton) stopButton.hidden = !server.online;
		if (restartButton) restartButton.hidden = !server.online;

		if (operation && operationLabel && operationMessage) {
			const copy = {
				starting: ["STARTING...", "Waiting for Minecraft server..."],
				stopping: ["STOPPING...", "Waiting for Minecraft server to shut down..."],
				restarting: ["RESTARTING...", operation.restartObservedOffline
					? "Minecraft stopped. Waiting for RCON to become available again..."
					: "Waiting for Minecraft to stop before it starts again..."],
			} as const;
			[operationLabel.textContent, operationMessage.textContent] = copy[operation.state];
		}

		if (controlError) controlError.hidden = errorMessage === null;
		if (errorMessageElement) errorMessageElement.textContent = errorMessage ?? "";
	};

	const render = (): void => {
		const displayValues = backendReachable
			? getServerDisplayValues(server)
			: getServerDisplayValues(createUnavailableMinecraftServer());
		setMetricValue("players", displayValues.players);
		setMetricValue("uptime", displayValues.uptime);
		setMetricValue("memory", displayValues.memory);
		setMetricValue("cpu", displayValues.cpu);
		renderStatus();
		renderPlayers();
		renderControls();
	};

	const failOperation = (message: string): void => {
		operation = null;
		lifecycle = "error";
		errorKind = "operation";
		errorMessage = message;
		render();
	};

	const checkOperationTimeout = (): void => {
		if (!operation || Date.now() < operation.deadline) return;
		const actionName = operation.action === "start"
			? "start"
			: operation.action === "stop" ? "shut down" : "restart";
		failOperation(
			`Minecraft did not ${actionName} within the expected time. Check the server, then retry or refresh its state.`,
		);
	};

	const applyAuthoritativeStatus = (nextServer: GameServer): void => {
		server = nextServer;
		backendReachable = true;

		if (errorKind === "connection") {
			errorKind = null;
			errorMessage = null;
		}

		if (operation?.actionAccepted) {
			if (operation.action === "start" && server.online) {
				operation = null;
				lifecycle = "online";
			} else if (operation.action === "stop" && !server.online) {
				operation = null;
				lifecycle = "offline";
			} else if (operation.action === "restart") {
				if (!server.online) operation.restartObservedOffline = true;
				if (server.online && operation.restartObservedOffline) {
					operation = null;
					lifecycle = "online";
				}
			}
		} else if (!operation && errorKind === null) {
			lifecycle = server.online ? "online" : "offline";
		}
	};

	const refreshMinecraftStatus = async (): Promise<void> => {
		checkOperationTimeout();
		if (requestInFlight) return;
		requestInFlight = true;

		try {
			const response = await getMinecraftStatus();
			applyAuthoritativeStatus(minecraftStatusToGameServer(response));
		} catch {
			backendReachable = false;
			server = createUnavailableMinecraftServer();
			if (!operation) {
				lifecycle = "error";
				errorKind = "connection";
				errorMessage = "Cannot reach the FastAPI backend. Check the API URL and backend service, then try again.";
			}
		} finally {
			requestInFlight = false;
			checkOperationTimeout();
			render();
		}
	};

	const actionRequest = (action: MinecraftAction): Promise<unknown> => {
		if (action === "start") return startMinecraftServer();
		if (action === "stop") return stopMinecraftServer();
		return restartMinecraftServer();
	};

	const beginOperation = async (action: MinecraftAction): Promise<void> => {
		if (operation) return;
		const states: Record<MinecraftAction, OperationState> = {
			start: "starting",
			stop: "stopping",
			restart: "restarting",
		};
		operation = {
			action,
			state: states[action],
			deadline: Date.now() + OPERATION_TIMEOUTS_MS[action],
			actionAccepted: false,
			restartObservedOffline: false,
		};
		lifecycle = operation.state;
		errorKind = null;
		errorMessage = null;
		render();

		try {
			await actionRequest(action);
			if (!operation || operation.action !== action) return;
			operation.actionAccepted = true;
			await refreshMinecraftStatus();
		} catch (error: unknown) {
			const detail = error instanceof Error ? error.message : "Unknown request error";
			failOperation(`Could not ${action} the Minecraft server. ${detail}`);
		}
	};

	root.querySelector<HTMLButtonElement>('[data-action="start"]')
		?.addEventListener("click", () => void beginOperation("start"));

	for (const button of root.querySelectorAll<HTMLButtonElement>("[data-open-confirmation]")) {
		button.addEventListener("click", () => {
			if (operation) return;
			const action = button.dataset.openConfirmation;
			if (action !== "stop" && action !== "restart") return;
			const dialog = root.querySelector<HTMLDialogElement>(`[data-confirmation="${action}"]`);
			const count = dialog?.querySelector<HTMLElement>("[data-modal-player-count]");
			if (count) count.textContent = String(server.players.online);
			dialog?.showModal();
		});
	}

	for (const button of root.querySelectorAll<HTMLButtonElement>("[data-confirm-action]")) {
		button.addEventListener("click", () => {
			const action = button.dataset.confirmAction;
			if (action === "stop" || action === "restart") void beginOperation(action);
		});
	}

	root.querySelector<HTMLButtonElement>("[data-refresh-state]")?.addEventListener("click", () => {
		errorKind = null;
		errorMessage = null;
		lifecycle = backendReachable ? (server.online ? "online" : "offline") : "error";
		render();
		void refreshMinecraftStatus();
	});

	render();
	void refreshMinecraftStatus();
	window.setInterval(() => void refreshMinecraftStatus(), POLL_INTERVAL_MS);
}
