# Servidor do PATO (uso em equipe, com login). Veja servidor/LEIAME.md.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-calc-nogui tesseract-ocr tesseract-ocr-por poppler-utils p7zip-full unar fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-opcionais.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && (grep -v '^#' requirements-opcionais.txt | grep -v pytest | xargs -r -n1 pip install --no-cache-dir || true)
COPY pato_app ./pato_app
ENV PATO_DADOS=/dados PATO_LOGIN=1 PYTHONUNBUFFERED=1
VOLUME /dados
EXPOSE 8000
CMD ["python", "-m", "pato_app", "--host", "0.0.0.0", "--porta", "8000", "--sem-navegador", "--login"]
