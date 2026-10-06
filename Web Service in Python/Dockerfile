FROM mcr.microsoft.com/dotnet/runtime:8.0

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

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "600", "app:app"]
