FROM rust:1.85 as builder
WORKDIR /app
RUN apt-get update && apt-get install -y protobuf-compiler libprotobuf-dev
COPY proto proto
COPY services/rust-optimizer services/rust-optimizer
RUN cp -r /usr/include/google proto/ || echo "Google protos not found in /usr/include"
RUN ls -R /app/proto
WORKDIR /app/services/rust-optimizer
RUN cargo build --release

FROM debian:bookworm-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libssl3 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/services/rust-optimizer/target/release/rust-optimizer .
CMD ["./rust-optimizer"]
