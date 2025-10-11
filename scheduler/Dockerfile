# FROM python
FROM python:3.11-slim-bullseye
WORKDIR /home/myapp
COPY requirement.txt /home/myapp/
RUN pip install -r requirement.txt
COPY database.py /home/myapp/
COPY producer.py /home/myapp/
COPY scheduler.py /home/myapp/
CMD python3 -u /home/myapp/scheduler.py