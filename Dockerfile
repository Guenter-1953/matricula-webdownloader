FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["gunicorn","--bind","0.0.0.0:5000","--workers","2","--threads","4","--timeout","300","app:app"]
