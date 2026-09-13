export interface MinecraftStatusResponse {
	online: boolean;
	players: number;
	max_players: number;
	player_names: string[];
	uptime: number;
	memory_mb: number;
	cpu_percent: number;
}

export interface MinecraftActionResponse {
	success: boolean;
}

export interface MinecraftConsoleLogsResponse {
	lines: string[];
	available: boolean;
	message: string | null;
}

export interface MinecraftCommandResponse {
	success: boolean;
	response: string;
}

export type MinecraftAction = "start" | "stop" | "restart";

export interface AuthUserResponse {
	name: string;
	is_admin: boolean;
}

export interface IdentifyResponse {
	requires_password: boolean;
	user: AuthUserResponse | null;
}

export interface AuthenticatedSessionResponse {
	authenticated: true;
	name: string;
	is_admin: boolean;
}

export interface AnonymousSessionResponse {
	authenticated: false;
	name: null;
	is_admin: false;
}

export type SessionResponse = AuthenticatedSessionResponse | AnonymousSessionResponse;
