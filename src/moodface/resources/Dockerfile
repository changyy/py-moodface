# Runs compile.exe (a .NET Framework program from Mi Create) under Wine.
# Built by `moodface compiler docker-build` (linux/amd64; emulated on Apple Silicon)
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    WINEDEBUG=-all \
    WINEPREFIX=/opt/wineprefix \
    WINEARCH=win64

RUN dpkg --add-architecture i386 \
 && apt-get update \
 && apt-get install -y --no-install-recommends wine wine32 wine64 ca-certificates curl xvfb xauth \
 && rm -rf /var/lib/apt/lists/*

# Debian bookworm 的 Wine 8.0 對應 wine-mono 7.4.0
RUN curl -fsSL -o /tmp/wine-mono.msi https://dl.winehq.org/wine/wine-mono/7.4.0/wine-mono-7.4.0-x86.msi \
 && wineboot --init \
 && wine msiexec /i /tmp/wine-mono.msi /qn \
 && wineserver -w \
 && rm /tmp/wine-mono.msi

WORKDIR /work
