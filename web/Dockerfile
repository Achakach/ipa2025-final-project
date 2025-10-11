# FROM python
FROM python:3.11-slim-bullseye
WORKDIR /home/myapp
RUN pip install flask
RUN pip install couchdb
RUN pip install pika
# RUN pip install pymongo
COPY ./static /home/myapp/static/
COPY ./templates /home/myapp/templates/
COPY sample_app.py /home/myapp/
EXPOSE 8080
CMD python3 /home/myapp/sample_app.py
