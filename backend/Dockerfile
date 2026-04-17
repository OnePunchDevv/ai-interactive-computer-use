FROM docker.io/ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_PRIORITY=high

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install \
    xvfb \
    xterm \
    xdotool \
    scrot \
    imagemagick \
    sudo \
    mutter \
    x11vnc \
    tint2 \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    curl \
    git \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libffi-dev \
    liblzma-dev \
    net-tools \
    netcat \
    procps \
    software-properties-common && \
    sudo add-apt-repository ppa:mozillateam/ppa && \
    apt-get install -y --no-install-recommends \
    firefox-esr \
    x11-apps \
    xpdf \
    gedit \
    xpaint \
    galculator \
    pcmanfm \
    unzip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN git clone --branch v1.5.0 https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone --branch v0.12.0 https://github.com/novnc/websockify /opt/noVNC/utils/websockify && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html && \
    ln -sf /opt/noVNC/utils/websockify/run /usr/local/bin/websockify

COPY backend/firefox-session-launcher.sh /usr/local/bin/firefox-esr
RUN chmod +x /usr/local/bin/firefox-esr && \
    ln -sf /usr/local/bin/firefox-esr /usr/local/bin/firefox && \
    ln -sf /usr/local/bin/firefox-esr /usr/bin/firefox-esr

ENV USERNAME=computeruse
ENV HOME=/home/$USERNAME

RUN useradd -m -s /bin/bash -d $HOME $USERNAME && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

USER computeruse
WORKDIR $HOME

RUN git clone https://github.com/pyenv/pyenv.git ~/.pyenv && \
    cd ~/.pyenv && src/configure && make -C src

ENV PYENV_ROOT="$HOME/.pyenv"
ENV PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"
ENV PYENV_VERSION=3.11.6

RUN eval "$(pyenv init -)" && \
    pyenv install $PYENV_VERSION && \
    pyenv global $PYENV_VERSION && \
    pyenv rehash

RUN python -m pip install --upgrade pip==23.1.2 setuptools==58.0.4 wheel==0.40.0 && \
    python -m pip config set global.disable-pip-version-check true

COPY --chown=$USERNAME:$USERNAME computer_use_demo/requirements.txt $HOME/computer_use_demo/requirements.txt
RUN python -m pip install -r $HOME/computer_use_demo/requirements.txt

COPY --chown=$USERNAME:$USERNAME backend/requirements.txt $HOME/backend/requirements.txt
RUN python -m pip install -r $HOME/backend/requirements.txt

COPY --chown=$USERNAME:$USERNAME computer_use_demo/ $HOME/computer_use_demo/
COPY --chown=$USERNAME:$USERNAME backend/app/ $HOME/backend/app/
COPY --chown=$USERNAME:$USERNAME image/.config/ $HOME/.config/

ENV DISPLAY_WIDTH=1024
ENV DISPLAY_HEIGHT=768
# Makes computer_use_demo importable without sys.path manipulation
ENV PYTHONPATH=$HOME

WORKDIR $HOME/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
