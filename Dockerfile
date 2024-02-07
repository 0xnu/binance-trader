FROM python:3.13.0a3-slim
ADD app/ /app
ADD db/ /db
aDD trader.py /app
ADD balance.py /app
RUN pip install requests
CMD [ "python", "/app/trader.py" ]
