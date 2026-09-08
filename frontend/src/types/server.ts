export interface ServerPlayers {
	online: number;
	max: number;
	names: string[];
}

export interface ServerMetrics {
	uptimeSeconds: number;
	memoryMb: number;
	cpuPercent: number;
}

export interface GameServer {
	id: string;
	name: string;
	game: string;
	version?: string;
	online: boolean;
	players: ServerPlayers;
	metrics: ServerMetrics;
}
