ARG MODEL_BASE_IMAGE=rain-risk-model:v2
FROM ${MODEL_BASE_IMAGE}

RUN python -m pip install --no-cache-dir prometheus-client==0.24.1
WORKDIR /opt/rain-serving
COPY monitored_scoring.py .
EXPOSE 8080
ENTRYPOINT ["python", "-m", "uvicorn", "monitored_scoring:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
