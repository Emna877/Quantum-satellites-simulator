# Threat Analysis Console in one container (Render, Hugging Face Spaces or any Docker host).
#   docker build -t quantum-satellites .
#   docker run -p 7860:7860 quantum-satellites   ->  http://localhost:7860
FROM python:3.13-slim

# Java 25 runtime for Orekit (the version the project is verified with).
COPY --from=eclipse-temurin:25-jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# Hugging Face Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python -m scripts.fetch_dependencies \
    && mkdir -p data/console_runs \
    && chown -R user:user /app

USER user
# Hosts such as Render set PORT; Hugging Face uses 7860.
EXPOSE 7860
CMD python -m scripts.serve_console --host 0.0.0.0 --port ${PORT:-7860}
