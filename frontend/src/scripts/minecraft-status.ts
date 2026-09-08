import { getMinecraftStatus } from "../lib/api";
import {
	createUnavailableMinecraftServer,
	minecraftStatusToGameServer,
} from "../lib/minecraft";
import { getServerDisplayValues } from "../lib/server-format";
import type { GameServer } from "../types/server";

const POLL_INTERVAL_MS = 5_000;
const minecraftCard = document.querySelector<HTMLElement>('[data-server-id="minecraft"]');

const setMetricValue = (
	card: HTMLElement,
	metric: "uptime" | "memory" | "cpu",
	value: string,
): void => {
	const valueElement = card.querySelector<HTMLElement>(`[data-metric="${metric}"] strong`);

	if (valueElement) {
		valueElement.textContent = value;
	}
};

const renderServer = (card: HTMLElement, server: GameServer): void => {
	const statusElement = card.querySelector<HTMLElement>(".server-status");
	const playerCountElement = card.querySelector<HTMLElement>("[data-player-count]");
	const displayValues = getServerDisplayValues(server);

	card.classList.toggle("offline", !server.online);

	if (statusElement) {
		const statusDot = document.createElement("span");
		statusDot.setAttribute("aria-hidden", "true");
		statusElement.classList.toggle("online", server.online);
		statusElement.classList.toggle("offline", !server.online);
		statusElement.replaceChildren(statusDot, server.online ? "Online" : "Offline");
	}

	if (playerCountElement) {
		playerCountElement.textContent = displayValues.players;
	}

	setMetricValue(card, "uptime", displayValues.uptime);
	setMetricValue(card, "memory", displayValues.memory);
	setMetricValue(card, "cpu", displayValues.cpu);
};

if (minecraftCard) {
	let requestInFlight = false;

	const refreshMinecraftStatus = async (): Promise<void> => {
		if (requestInFlight) {
			return;
		}

		requestInFlight = true;

		try {
			const response = await getMinecraftStatus();
			renderServer(minecraftCard, minecraftStatusToGameServer(response));
		} catch {
			renderServer(minecraftCard, createUnavailableMinecraftServer());
		} finally {
			requestInFlight = false;
		}
	};

	void refreshMinecraftStatus();
	window.setInterval(() => void refreshMinecraftStatus(), POLL_INTERVAL_MS);
}
