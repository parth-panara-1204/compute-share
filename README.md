## Compute Share

a dummy project, where you can share your compute via containers with those in your local network!

#### how to run?

1. on your host machine run ".venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000", after installing the dependencies.
2. now share "http://{your-ip}:8000" with those on your network.
3. they should be able to see a webpage, and through that be able to run containers on your machine.
4. after the creation of a container, they will be shown ssh command to connect to that container.
5. voila!
   
