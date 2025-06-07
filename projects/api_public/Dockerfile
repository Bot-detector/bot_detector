FROM python:3.11-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

ARG api_port
ENV UVICORN_PORT ${api_port}

ARG root_path
ENV UVICORN_ROOT_PATH ${root_path}

# set the working directory
WORKDIR /project

# install dependencies
COPY ./requirements.txt /project
RUN pip install --no-cache-dir -r requirements.txt

# copy the scripts to the folder
COPY ./src /project/src

# production image
FROM base AS production
# Creates a non-root user with an explicit UID and adds permission to access the /project folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /project
USER appuser

CMD ["uvicorn", "src.core.server:app", "--proxy-headers", "--host", "0.0.0.0", "--log-level", "warning"]