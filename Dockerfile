FROM ubuntu:latest

RUN apt-get update && apt-get install -y openssh-server

# Create necessary directory
RUN mkdir /var/run/sshd

# Configure SSH
RUN echo 'root:1234' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
EXPOSE 22

# Start SSH server
CMD ["/usr/sbin/sshd", "-D"]
