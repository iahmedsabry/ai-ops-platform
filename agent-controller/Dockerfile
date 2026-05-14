FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .

COPY prompt_modes/ ./prompt_modes/

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]