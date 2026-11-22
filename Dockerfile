# Blindgrasp sim server (MuJoCo + hosted TabPFN). The Next.js UI in web/ is deployed separately (Vercel).
FROM python:3.12-slim

# Headless MuJoCo rendering via OSMesa (CPU, no GPU or display needed); git to fetch the robot model.
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6 libgl1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa PYTHONUNBUFFERED=1 \
    BLINDGRASP_BACKEND=hosted BLINDGRASP_DEVICE=cpu HOST=0.0.0.0 PORT=8000

WORKDIR /app
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# Franka Panda meshes from MuJoCo Menagerie, pinned to the commit used in development.
ARG MENAGERIE_COMMIT=370c43965323c0944b433b202aac5058b5f907a9
RUN git clone --filter=blob:none --no-checkout https://github.com/google-deepmind/mujoco_menagerie.git \
    && cd mujoco_menagerie && git sparse-checkout set franka_emika_panda && git checkout $MENAGERIE_COMMIT \
    && rm -rf .git

COPY assets assets
COPY src src

# TABPFN_TOKEN comes from the platform's secret env vars, never from the image.
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
# Defaults suit Render's free tier (0.1 CPU): smaller, slower video. On a bigger plan set e.g. WIDTH=960 HEIGHT=600 FPS=15.
ENV WIDTH=640 HEIGHT=400 FPS=8 SPEED=2
CMD python -m src.web.server --mode script --learner tabpfn --width $WIDTH --height $HEIGHT --fps $FPS --speed $SPEED
