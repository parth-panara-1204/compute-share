import socket
import threading
import docker
import docker.errors
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
import psutil

app = FastAPI(title="Compute Share")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = docker.from_env()

CONTAINER_LABEL = "compute-share"
PORT_RANGE = range(2200, 2400)
port_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_lan_ip() -> str:
    """Return the LAN IP that other machines on the network can reach."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def find_free_port() -> int:
    """Return the next SSH host-port not already in use by a compute-share container."""
    used: set[int] = set()
    for c in client.containers.list(filters={"label": f"{CONTAINER_LABEL}=true"}):
        for binding in (c.ports.get("22/tcp") or []):
            used.add(int(binding["HostPort"]))
    for port in PORT_RANGE:
        if port not in used:
            return port
    raise RuntimeError("No free ports available in range 2200-2399")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SpawnRequest(BaseModel):
    cpu_cores: float = Field(default=1.0, ge=0.25, le=64.0, description="Number of CPU cores")
    memory_mb: int = Field(default=256, ge=64, le=65536, description="Memory limit in MB")
    label: str = Field(default="", max_length=64, description="Optional friendly name")


# ---------------------------------------------------------------------------
# Host info endpoint
# ---------------------------------------------------------------------------

@app.get("/api/host-info")
async def host_info():
    return {
        "cpu_cores": psutil.cpu_count(logical=True),
        "memory_total_mb": psutil.virtual_memory().total // (1024 * 1024),
        "memory_available_mb": psutil.virtual_memory().available // (1024 * 1024),
        "host_ip": get_lan_ip(),
    }


# ---------------------------------------------------------------------------
# Container endpoints
# ---------------------------------------------------------------------------

@app.post("/api/containers", status_code=201)
async def spawn_container(req: SpawnRequest):
    with port_lock:
        port = find_free_port()

    nano_cpus = int(req.cpu_cores * 1_000_000_000)
    mem_limit = f"{req.memory_mb}m"
    friendly = req.label.strip() or f"node-{port}"

    labels = {
        CONTAINER_LABEL: "true",
        f"{CONTAINER_LABEL}-label": friendly,
        f"{CONTAINER_LABEL}-cpu": str(req.cpu_cores),
        f"{CONTAINER_LABEL}-mem": str(req.memory_mb),
    }

    try:
        container = client.containers.run(
            "compute_share",
            mem_limit=mem_limit,
            nano_cpus=nano_cpus,
            ports={22: port},
            labels=labels,
            detach=True,
        )
    except docker.errors.ImageNotFound:
        raise HTTPException(status_code=500, detail="Docker image 'compute_share' not found. Build it first.")
    except docker.errors.APIError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    host_ip = get_lan_ip()
    return {
        "id": container.short_id,
        "name": friendly,
        "port": port,
        "ssh_command": f"ssh root@{host_ip} -p {port}",
        "ssh_password": "1234",
        "cpu_cores": req.cpu_cores,
        "memory_mb": req.memory_mb,
        "host_ip": host_ip,
    }


@app.get("/api/containers")
async def list_containers():
    host_ip = get_lan_ip()
    result = []
    for c in client.containers.list(filters={"label": f"{CONTAINER_LABEL}=true"}):
        bindings = c.ports.get("22/tcp") or []
        port = int(bindings[0]["HostPort"]) if bindings else None
        result.append({
            "id": c.short_id,
            "full_id": c.id,
            "name": c.labels.get(f"{CONTAINER_LABEL}-label", c.name),
            "status": c.status,
            "port": port,
            "ssh_command": f"ssh root@{host_ip} -p {port}" if port else None,
            "ssh_password": "1234",
            "cpu_cores": c.labels.get(f"{CONTAINER_LABEL}-cpu", "?"),
            "memory_mb": c.labels.get(f"{CONTAINER_LABEL}-mem", "?"),
            "created": c.attrs["Created"],
        })
    return result


@app.delete("/api/containers/{container_id}")
async def stop_container(container_id: str):
    try:
        c = client.containers.get(container_id)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")

    if c.labels.get(CONTAINER_LABEL) != "true":
        raise HTTPException(status_code=403, detail="Not a compute-share container")

    c.stop(timeout=5)
    c.remove()
    return {"message": "Container terminated"}


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

static_dir = Path(__file__).parent / "static"

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(static_dir / "index.html")
