FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY seed.py simulator.py main.py .

CMD ["python", "main.py"]
