FROM gcr.io/oss-fuzz-base/base-builder-rust@sha256:53c885625d133bff8a11b553f2098127f6bc92b4a1c6c23130c76cad8218b1c1

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*

COPY . $SRC/university_ecosystem
WORKDIR $SRC/university_ecosystem

COPY infra/oss-fuzz/build.sh $SRC/
RUN chmod +x "$SRC/build.sh"
