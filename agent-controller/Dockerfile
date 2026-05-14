FROM python:3.10-slim

WORKDIR /app

COPY agent-controller/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY shared ./shared
COPY agent_controller ./agent_controller
COPY agent-controller/app.py ./app.py

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
