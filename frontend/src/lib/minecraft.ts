import type { MinecraftStatusResponse } from "../types/api";
import type { GameServer } from "../types/server";

const minecraftIdentity = {
	id: "minecraft",
	name: "Minecraft",
	game: "Minecraft",
	version: "26.1.2",
} as const;

export const createUnavailableMinecraftServer = (): GameServer => ({
	...minecraftIdentity,
	online: false,
	players: {
		online: 0,
		max: 0,
		names: [],
	},
	metrics: {
		uptimeSeconds: 0,
		memoryMb: 0,
		cpuPercent: 0,
	},
});

export const minecraftStatusToGameServer = (
	status: MinecraftStatusResponse,
): GameServer => ({
	...minecraftIdentity,
	online: status.online,
	players: {
		online: status.players,
		max: status.max_players,
		names: status.player_names,
	},
	metrics: {
		uptimeSeconds: status.uptime,
		memoryMb: status.memory_mb,
		cpuPercent: status.cpu_percent,
	},
});
