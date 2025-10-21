#!/usr/bin/env bash
# Setup script (Linux / WSL). On Windows, run equivalent commands in PowerShell.

echo "This script outlines installation steps. Run parts manually on Windows as needed."

echo "1) Install Python 3.10+"
# ubuntu example
echo "sudo apt update; sudo apt install -y python3.10 python3.10-venv python3.10-dev"

echo "2) Create virtualenv and install backend dependencies"
echo "python3.10 -m venv venv; source venv/bin/activate; pip install -r backend/requirements.txt"

echo "3) Install Node.js and npm (for frontend/Cesium)"
echo "Refer to https://nodejs.org/"

echo "4) Java 11+ and Maven for Orekit"
echo "sudo apt install -y openjdk-11-jdk maven"

echo "5) Qiskit"
echo "pip install qiskit"

echo "6) PyTorch"
echo "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"

echo "7) Optional: install http-server for frontend demo"
echo "npm install -g http-server"

echo "Done. See README.md for example commands."
