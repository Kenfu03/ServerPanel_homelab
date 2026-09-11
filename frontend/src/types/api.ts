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

export type MinecraftAction = "start" | "stop" | "restart";
