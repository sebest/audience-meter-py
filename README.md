A quick reimplemtation of https://github.com/rs/audience-meter in python using gunicorn, gevent and WebSocket

Warning: Highly untested!

To run it:
gunicorn -w 1 -b 0.0.0.0:8000 -k gevent audience_meter:app
