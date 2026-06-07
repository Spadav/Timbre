FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git git-lfs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir ".[all]"

EXPOSE 9000
CMD ["timbre", "serve", "--host", "0.0.0.0", "--port", "9000"]
