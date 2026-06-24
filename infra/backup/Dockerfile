# Tiny container that runs pg_dump on a cron, plus an optional rclone push
# to a remote (B2, S3, etc). Built locally — never published to GHCR.

FROM alpine:3.20

RUN apk add --no-cache \
        postgresql16-client \
        bash \
        coreutils \
        tzdata \
        gzip \
        rclone

COPY run.sh /usr/local/bin/run.sh
RUN chmod +x /usr/local/bin/run.sh

ENV PATH="/usr/local/bin:$PATH"
WORKDIR /backups

CMD ["/usr/local/bin/run.sh"]
