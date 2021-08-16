#!/bin/ash

# Setup git
git config --global user.email "$GIT_EMAIL"
git config --global user.name "$GIT_NAME"

# Create deploy key for access to the acmi-api repo
mkdir -p ~/.ssh
echo "$SSH_PRIVATE_KEY" > ~/.ssh/id_rsa
echo "$SSH_KNOWN_HOSTS" > ~/.ssh/known_hosts
chmod 600 ~/.ssh/id_rsa

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
