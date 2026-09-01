# Base image matches the Python version pinned in .github/workflows/tests.yml
# (3.12), so behavior verified in CI matches behavior in this image.
FROM python:3.12-slim

WORKDIR /app

# Copy only requirements.txt first so the pip-install layer is cached and
# doesn't get invalidated by unrelated source changes.
COPY source_code/requirements.txt source_code/requirements.txt
RUN pip install --no-cache-dir -r source_code/requirements.txt

# Copy the rest of the repo. .dockerignore keeps secrets, tests, docs, and
# other non-runtime content out of the image.
COPY . .

# .streamlit/config.toml and (if present) secrets.toml are resolved by
# Streamlit relative to the process's working directory - invoking with a
# path (source_code/app.py) from /app, rather than cd-ing into source_code/
# first, is what makes that resolution find /app/.streamlit/.
# database.py/llm_provider.py/tracing.py separately read secrets.toml
# anchored to their own file location, so that part works regardless of
# WORKDIR - this choice is specifically for config.toml (theme/server
# settings).
#
# Never bake real secrets into the image: .streamlit/secrets.toml is
# excluded via .dockerignore. Pass DB/LangSmith/Groq credentials and
# OLLAMA_BASE_URL at `docker run` time via -e or --env-file instead.
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

CMD ["streamlit", "run", "source_code/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
