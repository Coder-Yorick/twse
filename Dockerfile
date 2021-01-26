FROM python:3.7

COPY ./requirements.txt /app/requirements.txt
WORKDIR /app
RUN apt update -y
RUN apt install -y libgl1-mesa-glx
RUN apt-get install -y tesseract-ocr
RUN pip install -r requirements.txt
COPY . /app
CMD ["python", "main.py"]
