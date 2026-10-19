# The explorer in a container, over the releases in /data.
#
#   docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD:/data" ghcr.io/altio-ai/open-altio
#   docker run --rm -p 127.0.0.1:8000:8000 -v open-altio:/data ghcr.io/altio-ai/open-altio demo --no-open
#
# The first serves the newest release in the current folder; the second builds the demo into a
# volume and serves it. Either way the explorer is at http://127.0.0.1:8000.
#
# Why it listens on 0.0.0.0 here and only here: inside a container 127.0.0.1 is the container's
# own address, which the host cannot reach. A container's port is reachable only where
# `docker run -p` publishes it, and the commands above publish it on the host's 127.0.0.1
# alone, so, as outside a container, only this machine reaches the explorer.

FROM python:3.12-slim AS wheel
WORKDIR /src
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src src
COPY rules rules
COPY mappings mappings
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /dist .

FROM python:3.12-slim
COPY --from=wheel /dist /dist
RUN pip install --no-cache-dir /dist/*.whl \
    && rm -r /dist \
    && useradd --create-home --uid 1000 altio \
    && mkdir /data && chown altio /data
USER altio
ENV OPEN_ALTIO_DATA_DIR=/data OPEN_ALTIO_HOST=0.0.0.0
WORKDIR /data
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["open-altio"]
CMD ["serve", "--no-open", "--port", "8000"]
