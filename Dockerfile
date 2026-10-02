FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/app/data PORT=8080
WORKDIR /app
RUN useradd --uid 1000 --create-home business && mkdir /app/data && chown business:business /app/data
COPY --chown=business:business app.py engine.py manage.py ./
COPY --chown=business:business static ./static
USER business
EXPOSE 8080
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('SERVER_PORT',os.getenv('PORT','8080'))+'/health',timeout=2)" || exit 1
CMD ["python", "app.py"]
