#!/bin/ash

# Setup git
git config --global user.email "$GIT_EMAIL"
git config --global user.name "$GIT_NAME"
git remote set-url origin git@github.com:ACMILabs/acmi-api.git

# Create deploy key for access to the acmi-api repo
mkdir -p ~/.ssh
echo -e "$SSH_PRIVATE_KEY" > ~/.ssh/id_rsa
echo -e "$SSH_KNOWN_HOSTS" > ~/.ssh/known_hosts
chmod 600 ~/.ssh/id_rsa

if [ "$CRON_UPDATER" = "true" ]; then
    crond
fi

# Download the tarball using wget
wget https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz
tar xzf litestream-v0.3.13-linux-amd64.tar.gz
mv litestream /usr/local/bin/litestream
chmod +x /usr/local/bin/litestream
rm litestream-v0.3.13-linux-amd64.tar.gz

# Setup S3 access
export LITESTREAM_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
export LITESTREAM_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

# Download the latest database from S3
echo "Downloading latest database from S3..."
litestream restore -o /code/app/instance/${SUGGESTIONS_DATABASE}.db s3://acmi-public-api/${SUGGESTIONS_DATABASE}.db

# Start Litestream replication in the background
echo "Starting Litestream replication..."
litestream replicate /code/app/instance/${SUGGESTIONS_DATABASE}.db s3://acmi-public-api/${SUGGESTIONS_DATABASE}.db &

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
        --timeout 120 \
        --reload
fi
