#!/bin/bash
cd frontend
npm install
npm run build
cd ..
mkdir -p static
cp -r frontend/build/* static/
