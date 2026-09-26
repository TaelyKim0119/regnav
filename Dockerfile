# Runs locally, on Nebius AI Cloud, or as a Hugging Face Docker Space.
# The port comes from $PORT (default 7860, the Hugging Face Spaces convention).
FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .
USER user
ENV PORT=7860 PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["python", "app.py"]
