import type { GameServer } from "../types/server";

export interface ServerDisplayValues {
	players: string;
	uptime: string;
	memory: string;
	cpu: string;
}

export const formatUptime = (totalSeconds: number): string => {
	const totalMinutes = Math.floor(totalSeconds / 60);
	const hours = Math.floor(totalMinutes / 60);
	const minutes = totalMinutes % 60;

	return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
};

export const formatMemory = (memoryMb: number): string => {
	return memoryMb >= 1024 ? `${(memoryMb / 1024).toFixed(1)} GB` : `${memoryMb} MB`;
};

export const getServerDisplayValues = (server: GameServer): ServerDisplayValues => {
	if (!server.online) {
		return {
			players: "--",
			uptime: "--",
			memory: "--",
			cpu: "--",
		};
	}

	return {
		players: `${server.players.online} / ${server.players.max}`,
		uptime: formatUptime(server.metrics.uptimeSeconds),
		memory: formatMemory(server.metrics.memoryMb),
		cpu: `${server.metrics.cpuPercent}%`,
	};
};
