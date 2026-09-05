# Base image: python:3.12-slim. Standard-library app, no pip install needed at build time.
FROM python:3.12-slim
WORKDIR /app
COPY appealpal ./appealpal
COPY fixtures ./fixtures

# Public, card-free hosting defaults: bind all interfaces, allow non-loopback binding, and run
# with the in-process fake model (demo mode) unless the platform overrides APPEALPAL_DEMO=0 and
# supplies LLM_API_KEY/LLM_BASE_URL/LLM_MODEL. PORT is read at runtime by appealpal/web.py
# (`os.environ.get("PORT", ...)`); Render (and most PaaS) inject their own PORT value, which
# overrides this image default automatically.
ENV HOST=0.0.0.0 PORT=8810 APPEALPAL_PUBLIC=1 APPEALPAL_DEMO=1
EXPOSE 8810
CMD ["python3", "-m", "appealpal"]

# NOTE: this image build was not verified in this environment because Docker Desktop is not
# running here (`docker info` fails to reach the daemon socket). The Dockerfile only adds two
# COPY layers and three ENV defaults on top of the stock python:3.12-slim image and changes
# nothing the test suite doesn't already exercise (same `python3 -m appealpal` entrypoint used
# in local runs), but it has not been built or run as a container in this session. Verify with
# `docker build -t appealpal . && docker run -p 8810:8810 appealpal` before relying on it.
