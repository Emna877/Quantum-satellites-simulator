FROM pytorch/pytorch:1.13.1-cuda11.6-cudnn8-runtime
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
CMD ["python", "model_train.py"]
