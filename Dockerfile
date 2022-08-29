FROM python:latest

WORKDIR /code

COPY . .

RUN pip install -r requirements.txt

CMD [ "python", "./bot.py" ]
