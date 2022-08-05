#!/usr/bin/bash
mkdir -p in out
rm -rf out/*
docker build -t udis .
docker run -it -v $PWD/in:/code/in -v $PWD/out:/code/out udis
