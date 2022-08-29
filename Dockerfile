FROM python:latest

WORKDIR /code

COPY . .

RUN pip install -r requirements.txt

# Uncomment to run directly from Docker
#CMD [ "python", "./bot.py" ]
