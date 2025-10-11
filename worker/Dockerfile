# FROM python
FROM python:3.11-slim-bullseye
WORKDIR /home/myapp
COPY . /home/myapp
RUN pip install -r requirements.txt

# ENV ANSIBLE_LIBRARY ... <-- ลบบรรทัดนี้ออก

RUN ansible-galaxy collection install cisco.ios
CMD python3 -u /home/myapp/worker.py