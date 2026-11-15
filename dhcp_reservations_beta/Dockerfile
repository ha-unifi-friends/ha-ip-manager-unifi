ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3

WORKDIR /app
COPY app/ /app/
COPY config.yaml /app/config.yaml

CMD ["python3", "-u", "/app/server.py"]
