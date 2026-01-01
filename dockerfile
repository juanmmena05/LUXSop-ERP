FROM python:3.11-slim

# Dependencias para wkhtmltopdf + fuentes (para que el PDF no falle)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    fontconfig \
    xfonts-75dpi \
    xfonts-base \
    libjpeg62-turbo \
    libx11-6 \
    libxext6 \
    libxrender1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# En Linux wkhtmltopdf normalmente vive aquí
ENV WKHTMLTOPDF_CMD=/usr/bin/wkhtmltopdf

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "wsgi:app"]
