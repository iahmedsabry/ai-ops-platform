FROM python:3.10-slim

WORKDIR /app

COPY agent-sandbox/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY shared ./shared
COPY agent_sandbox ./agent_sandbox
COPY agent-sandbox/app.py ./app.py

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
