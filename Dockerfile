# ---- 1. Build Vue frontend ----
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- 2. Publish .NET wrapper ----
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS dotnet
WORKDIR /src
COPY "NETStandardWrapperLibrary/WebServiceLibrary/" ./
RUN dotnet publish WebServiceLibrary.csproj -c Release
# output: /src/bin/Release/net10.0/publish/

# ---- 3. Runtime ----
FROM mcr.microsoft.com/dotnet/runtime:10.0

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    curl \
    libgdiplus \
    fontconfig \
    libfreetype6 \
    libharfbuzz0b \
    libfontconfig1 \
    libssl3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONNET_RUNTIME=coreclr
ENV DOTNET_ROOT=/usr/share/dotnet

WORKDIR /app

COPY . .

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY Files ./Files
COPY --from=frontend /fe/dist ./frontend/dist
COPY --from=dotnet /src/bin/Release/net10.0/publish "./NETStandardWrapperLibrary/WebServiceLibrary/bin/Release/net10.0/publish/"

EXPOSE 5000

CMD ["gunicorn","--bind","0.0.0.0:5000","--timeout","600","--workers","1","--threads","4","app:app"]
