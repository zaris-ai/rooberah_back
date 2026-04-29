FROM python:3.12-slim

ENV HOME=/home/app/parking 
#example: /home/app/starbot 
RUN mkdir -p $HOME 

ENV PYTHONUNBUFFERED=1


# Set working directory
WORKDIR $HOME
COPY . $HOME

# Installing requirements
RUN pip install --upgrade pip && \
    pip install -r requirements.txt --no-cache-dir

# Collect static files - will run after volumes are mounted

CMD ["sh", "-c", "python manage.py migrate --no-input && python manage.py collectstatic --no-input && gunicorn -b 0.0.0.0:8000 config.wsgi:application --workers 3 --timeout 120"]