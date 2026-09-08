import type { MinecraftStatusResponse } from "../types/api";

const REQUEST_TIMEOUT_MS = 4_000;

const isFiniteNumber = (value: unknown): value is number => {
	return typeof value === "number" && Number.isFinite(value);
};

const isMinecraftStatusResponse = (value: unknown): value is MinecraftStatusResponse => {
	if (typeof value !== "object" || value === null) {
		return false;
	}

	const response = value as Record<string, unknown>;

	return (
		typeof response.online === "boolean" &&
		isFiniteNumber(response.players) &&
		isFiniteNumber(response.max_players) &&
		Array.isArray(response.player_names) &&
		response.player_names.every((name: unknown) => typeof name === "string") &&
		isFiniteNumber(response.uptime) &&
		isFiniteNumber(response.memory_mb) &&
		isFiniteNumber(response.cpu_percent)
	);
};

const getApiBaseUrl = (): string => {
	const apiBaseUrl = import.meta.env.PUBLIC_API_URL?.trim();

	if (!apiBaseUrl) {
		throw new Error("PUBLIC_API_URL is not configured");
	}

	return apiBaseUrl.replace(/\/+$/, "");
};

export const getMinecraftStatus = async (): Promise<MinecraftStatusResponse> => {
	const response = await fetch(`${getApiBaseUrl()}/api/status`, {
		headers: {
			Accept: "application/json",
		},
		cache: "no-store",
		signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
	});

	if (!response.ok) {
		throw new Error(`Minecraft status request failed with HTTP ${response.status}`);
	}

	const data: unknown = await response.json();

	if (!isMinecraftStatusResponse(data)) {
		throw new Error("Minecraft status response has an unexpected shape");
	}

	return data;
};
