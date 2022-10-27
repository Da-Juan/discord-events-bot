FROM python:3.10-slim as base

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1


FROM base AS python-deps

# Install pipenv and compilation dependencies
RUN pip install pipenv
RUN apt-get update && apt-get install -y --no-install-recommends gcc

RUN mkdir /app
WORKDIR /app

# Install python dependencies in .venv
COPY Pipfile* /app/
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy
COPY . .
RUN /app/.venv/bin/pip install .


FROM base AS runtime

# Copy virtual env from python-deps stage
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Create and switch to a new user
RUN useradd --create-home bot
WORKDIR /home/bot

USER bot

# Run the application
ENTRYPOINT ["eventsbot", "-v", "/config.yaml"]
