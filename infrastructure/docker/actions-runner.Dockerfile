FROM python:3.12-slim-bookworm
ARG RUNNER_URL
ARG RUNNER_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git libicu72 libssl3 libkrb5-3 zlib1g \
    libunwind8 liblttng-ust1 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.11.28 \
    && useradd --create-home --uid 1000 runner
WORKDIR /home/runner
RUN test -n "$RUNNER_URL" && test -n "$RUNNER_SHA256" \
    && curl --fail --location --retry 3 "$RUNNER_URL" --output /tmp/runner.tar.gz \
    && echo "$RUNNER_SHA256  /tmp/runner.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/runner.tar.gz \
    && rm /tmp/runner.tar.gz \
    && chown -R runner:runner /home/runner
USER runner
# config.sh is executed separately, with the one-hour registration token on stdin.
CMD ["bash", "-c", "while [ ! -f .configured ]; do sleep 1; done; exec ./run.sh"]
