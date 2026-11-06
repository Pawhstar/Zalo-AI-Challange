FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONUTF8=1 \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY datamate/ ./datamate/
COPY predict.sh README.md ./
RUN sed -i 's/\r$//' predict.sh && chmod +x predict.sh

# the organisers mount the test folder at /data and collect /result
VOLUME ["/data", "/result"]
ENTRYPOINT ["/app/predict.sh"]
