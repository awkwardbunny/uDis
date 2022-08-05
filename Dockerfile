FROM python:3.10.6-bullseye

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN mkdir -p /code
WORKDIR /code
COPY . /code
RUN pip3 install -r requirements.txt

CMD ./main.py in out
