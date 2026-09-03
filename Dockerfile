FROM python:3.12-slim
WORKDIR /app
COPY appealpal ./appealpal
COPY fixtures ./fixtures
ENV HOST=0.0.0.0 PORT=7860 APPEALPAL_PUBLIC=1
EXPOSE 7860
CMD ["python3", "-m", "appealpal"]
