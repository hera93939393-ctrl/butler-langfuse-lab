FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY static static
COPY mock_data mock_data
ENV PORT=8080
# exec: Cloud Run 이 보내는 종료 신호(SIGTERM)가 uvicorn 에 바로 가서, 하던 요청을 마치고 끈다
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
