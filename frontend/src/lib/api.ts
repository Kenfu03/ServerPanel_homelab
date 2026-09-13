import type {
	MinecraftAction,
	MinecraftActionResponse,
	MinecraftCommandResponse,
	MinecraftConsoleLogsResponse,
	MinecraftStatusResponse,
	IdentifyResponse,
} from "../types/api";
import type { CurrentUser } from "../types/auth";

const STATUS_REQUEST_TIMEOUT_MS = 4_000;
const ACTION_REQUEST_TIMEOUT_MS = 30_000;
const API_REQUEST_CREDENTIALS: RequestCredentials = "include";

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

    if (import.meta.env.DEV) {
        if (!apiBaseUrl) {
            throw new Error("PUBLIC_API_URL is not configured");
        }

        return apiBaseUrl.replace(/\/+$/, "");
    }

    return "";
};

const apiFetch = (path: string, init: RequestInit = {}): Promise<Response> => {
	return fetch(`${getApiBaseUrl()}${path}`, {
		...init,
		credentials: API_REQUEST_CREDENTIALS,
	});
};

const isAuthUserResponse = (value: unknown): value is IdentifyResponse["user"] => {
	if (value === null) return true;
	if (typeof value !== "object") return false;
	const user = value as Record<string, unknown>;
	return typeof user.name === "string" && typeof user.is_admin === "boolean";
};

const readJson = async (response: Response, requestName: string): Promise<unknown> => {
	if (!response.ok) {
		throw new Error(`${requestName} failed with HTTP ${response.status}`);
	}
	return response.json();
};

export const getMinecraftStatus = async (): Promise<MinecraftStatusResponse> => {
	const response = await apiFetch("/api/status", {
		headers: {
			Accept: "application/json",
		},
		cache: "no-store",
		signal: AbortSignal.timeout(STATUS_REQUEST_TIMEOUT_MS),
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

const sendMinecraftAction = async (
	action: MinecraftAction,
): Promise<MinecraftActionResponse> => {
	const response = await apiFetch(`/api/${action}`, {
		method: "POST",
		headers: {
			Accept: "application/json",
		},
		cache: "no-store",
		signal: AbortSignal.timeout(ACTION_REQUEST_TIMEOUT_MS),
	});

	if (!response.ok) {
		throw new Error(`Minecraft ${action} request failed with HTTP ${response.status}`);
	}

	const data: unknown = await response.json();

	if (
		typeof data !== "object" ||
		data === null ||
		typeof (data as Record<string, unknown>).success !== "boolean"
	) {
		throw new Error(`Minecraft ${action} response has an unexpected shape`);
	}

	const actionResponse = data as MinecraftActionResponse;

	if (!actionResponse.success) {
		throw new Error(`The backend could not ${action} the Minecraft service`);
	}

	return actionResponse;
};

export const startMinecraftServer = (): Promise<MinecraftActionResponse> =>
	sendMinecraftAction("start");

export const stopMinecraftServer = (): Promise<MinecraftActionResponse> =>
	sendMinecraftAction("stop");

export const restartMinecraftServer = (): Promise<MinecraftActionResponse> =>
	sendMinecraftAction("restart");

export const getMinecraftConsoleLogs = async (): Promise<MinecraftConsoleLogsResponse> => {
	const response = await apiFetch("/api/console/logs", {
		headers: { Accept: "application/json" },
		cache: "no-store",
		signal: AbortSignal.timeout(STATUS_REQUEST_TIMEOUT_MS),
	});
	const data = await readJson(response, "Minecraft console logs request");

	if (typeof data !== "object" || data === null) {
		throw new Error("Minecraft console logs response has an unexpected shape");
	}
	const result = data as Record<string, unknown>;
	if (
		!Array.isArray(result.lines) ||
		!result.lines.every((line: unknown) => typeof line === "string") ||
		typeof result.available !== "boolean" ||
		!(typeof result.message === "string" || result.message === null)
	) {
		throw new Error("Minecraft console logs response has an unexpected shape");
	}

	return {
		lines: result.lines,
		available: result.available,
		message: result.message,
	};
};

export const sendMinecraftCommand = async (
	command: string,
): Promise<MinecraftCommandResponse> => {
	const response = await apiFetch("/api/console/command", {
		method: "POST",
		headers: { "Content-Type": "application/json", Accept: "application/json" },
		body: JSON.stringify({ command }),
		signal: AbortSignal.timeout(ACTION_REQUEST_TIMEOUT_MS),
	});
	const data = await readJson(response, "Minecraft console command");

	if (typeof data !== "object" || data === null) {
		throw new Error("Minecraft console command response has an unexpected shape");
	}
	const result = data as Record<string, unknown>;
	if (result.success !== true || typeof result.response !== "string") {
		throw new Error("Minecraft console command response has an unexpected shape");
	}

	return { success: true, response: result.response };
};

export const identifyUser = async (name: string): Promise<IdentifyResponse> => {
	const response = await apiFetch("/api/auth/identify", {
		method: "POST",
		headers: { "Content-Type": "application/json", Accept: "application/json" },
		body: JSON.stringify({ name }),
		signal: AbortSignal.timeout(STATUS_REQUEST_TIMEOUT_MS),
	});
	const data = await readJson(response, "Identity request");

	if (typeof data !== "object" || data === null) {
		throw new Error("Identity response has an unexpected shape");
	}
	const result = data as Record<string, unknown>;
	if (typeof result.requires_password !== "boolean" || !isAuthUserResponse(result.user)) {
		throw new Error("Identity response has an unexpected shape");
	}
	return {
		requires_password: result.requires_password,
		user: result.user,
	};
};

export const loginAdmin = async (name: string, password: string): Promise<CurrentUser> => {
	const response = await apiFetch("/api/auth/login", {
		method: "POST",
		headers: { "Content-Type": "application/json", Accept: "application/json" },
		body: JSON.stringify({ name, password }),
		signal: AbortSignal.timeout(STATUS_REQUEST_TIMEOUT_MS),
	});
	const data = await readJson(response, "Admin sign-in");

	if (typeof data !== "object" || data === null) {
		throw new Error("Admin sign-in response has an unexpected shape");
	}
	const result = data as Record<string, unknown>;
	if (result.authenticated !== true || typeof result.name !== "string" || result.is_admin !== true) {
		throw new Error("Admin sign-in response has an unexpected shape");
	}
	return { name: result.name, isAdmin: true };
};

export const getCurrentUser = async (): Promise<CurrentUser | null> => {
	const response = await apiFetch("/api/auth/me", {
		headers: { Accept: "application/json" },
		cache: "no-store",
		signal: AbortSignal.timeout(STATUS_REQUEST_TIMEOUT_MS),
	});
	const data = await readJson(response, "Session request");

	if (typeof data !== "object" || data === null) {
		throw new Error("Session response has an unexpected shape");
	}
	const result = data as Record<string, unknown>;
	if (result.authenticated === false && result.name === null && result.is_admin === false) {
		return null;
	}
	if (result.authenticated === true && typeof result.name === "string" && typeof result.is_admin === "boolean") {
		return { name: result.name, isAdmin: result.is_admin };
	}
	throw new Error("Session response has an unexpected shape");
};

export const logoutUser = async (): Promise<void> => {
	const response = await apiFetch("/api/auth/logout", {
		method: "POST",
		headers: { Accept: "application/json" },
		signal: AbortSignal.timeout(STATUS_REQUEST_TIMEOUT_MS),
	});
	await readJson(response, "Sign out request");
};
