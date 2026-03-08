""".venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000"""

import docker

def main():
    print("Hello from docker-compute-share!")

    port = 2222
    cpu = 2_000_000_000
    mem = "128m"

    client = docker.from_env()
    output = client.containers.run("compute_share", mem_limit=mem, nano_cpus=cpu, ports={22:port}, detach=True)

if __name__ == "__main__":
    main()
