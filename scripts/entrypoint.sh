#!/bin/ash

if [ "$CRON_UPDATER" = "true" ]; then
    crond
fi

if [ "$DEBUG" = "true" ]; then
    echo "Starting Flask server..."
    python -u -m app.api
else
    echo "Starting gunicorn server..."
    PYTHON_PATH=`python -c "import sys; print(sys.path[-1])"`
    gunicorn app.api \
        --log-level DEBUG \
        --pythonpath $PYTHON_PATH \
        --workers 2 \
        --bind 0.0.0.0:8081 \
        --reload
fi
