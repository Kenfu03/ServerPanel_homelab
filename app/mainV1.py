import subprocess

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


def minecraft_command(action: str):
    allowed_actions = {"start", "stop", "restart"}

    if action not in allowed_actions:
        return False

    result = subprocess.run(
        ["sudo", "-n", "/usr/bin/systemctl", action, "minecraft"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Command failed: {result.stderr}")

    return result.returncode == 0


def minecraft_status():
    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "minecraft"],
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()


@app.get("/api/status")
def status():
    return {"status": minecraft_status()}


@app.post("/api/start")
def start():
    return {"success": minecraft_command("start")}


@app.post("/api/stop")
def stop():
    return {"success": minecraft_command("stop")}


@app.post("/api/restart")
def restart():
    return {"success": minecraft_command("restart")}


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Minecraft Homelab</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            background: #151515;
            color: white;
            text-align: center;
            margin-top: 100px;
        }

        .panel {
            width: 400px;
            margin: auto;
            background: #222;
            padding: 30px;
            border-radius: 15px;
        }

        button {
            padding: 12px 20px;
            margin: 5px;
            font-size: 16px;
            cursor: pointer;
        }

        button:disabled {
            cursor: not-allowed;
            opacity: 0.5;
        }

        #status {
            font-size: 24px;
            margin: 25px;
        }

        #message {
            min-height: 20px;
            margin-top: 15px;
        }
    </style>
</head>

<body>

<div class="panel">

    <h1>Minecraft Server</h1>

    <div id="status">Checking...</div>

    <button id="startButton" onclick="sendCommand('start')">
        Start
    </button>

    <button id="stopButton" onclick="sendCommand('stop')">
        Stop
    </button>

    <button id="restartButton" onclick="sendCommand('restart')">
        Restart
    </button>

    <div id="message"></div>

</div>

<script>
    async function updateStatus() {
        try {
            const response = await fetch('/api/status', {
                cache: 'no-store'
            });

            const data = await response.json();
            const statusElement = document.getElementById('status');

            if (data.status === 'active') {
                statusElement.textContent = '🟢 ONLINE';
            } else {
                statusElement.textContent = '🔴 OFFLINE';
            }
        } catch (error) {
            console.error('Status error:', error);
            document.getElementById('status').textContent = '⚠️ ERROR';
        }
    }


    async function sendCommand(action) {
        console.log('Sending:', action);

        const message = document.getElementById('message');

        message.textContent = 'Sending command...';

        try {
            const response = await fetch('/api/' + action, {
                method: 'POST'
            });

            const data = await response.json();

            console.log('Response:', data);

            if (data.success) {
                message.textContent = action + ' command sent successfully.';
            } else {
                message.textContent = 'Command failed.';
            }

            setTimeout(updateStatus, 1000);

        } catch (error) {
            console.error('Command error:', error);
            message.textContent = 'Request failed.';
        }
    }


    updateStatus();

    setInterval(updateStatus, 5000);
</script>

</body>
</html>
"""
