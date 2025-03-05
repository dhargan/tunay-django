# Gunicorn configuration file for a single-page Django project
# This configuration is optimized for minimal resource usage.

import os

# Bind Gunicorn to the provided PORT (important for Heroku deployment)
bind = "0.0.0.0:{}".format(os.environ.get("PORT", "8000"))

# Set the number of worker processes
# Since this is a single-page application, one worker should be sufficient
workers = 1

# Set a reasonable timeout to avoid long-running requests hanging
timeout = 60

# Define log levels for debugging and monitoring
loglevel = "info"

# Direct logs to standard output, useful for cloud platforms like Heroku
accesslog = "-"
errorlog = "-"

# Ensure Gunicorn runs in the foreground (Heroku requires this)
daemon = False
