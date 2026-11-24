FROM ubuntu:24.04

LABEL org.opencontainers.image.title="HelioStack OpenFOAM 14 PV Thermal Sweep" \
      org.opencontainers.image.description="Reproducible OpenFOAM 14 28-deg tilted PV convective cooling & Floating-PV runner" \
      org.opencontainers.image.source="https://github.com/ttthkim-hue/heliostack" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

ARG DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg; \
    mkdir -p /usr/share/keyrings; \
    curl -fsSL https://dl.openfoam.org/gpg.key -o /tmp/openfoam.key; \
    gpg --batch --yes --dearmor -o /usr/share/keyrings/openfoam.gpg /tmp/openfoam.key; \
    rm -f /tmp/openfoam.key; \
    echo "deb [signed-by=/usr/share/keyrings/openfoam.gpg] http://dl.openfoam.org/ubuntu noble main" \
      > /etc/apt/sources.list.d/openfoam.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends openfoam14 python3 python3-numpy; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY run_openfoam_pv_sweep.py /work/openfoam/run_openfoam_pv_sweep.py

CMD ["python3", "/work/openfoam/run_openfoam_pv_sweep.py", "--native", "--smoke", "--out", "/tmp/openfoam_smoke_receipt.json"]
