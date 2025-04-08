FROM debian:bookworm-20240722-slim

RUN apt-get update && apt-get install -y stress && rm -rf /var/lib/apt/lists/*

CMD ["stress", "--cpu", "1"]
