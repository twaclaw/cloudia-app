FROM python:3.11-alpine
WORKDIR /code
EXPOSE 1883
COPY conf.yaml .
COPY src src
RUN pip install -e src

CMD ["python", "-m", "app.main",  "conf.yaml"]