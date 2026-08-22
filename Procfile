release: python manage.py migrate --noinput
web: gunicorn --config gunicorn.conf.py tunay.wsgi
