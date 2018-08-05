#!/bin/bash

name="Linux Inside на русском"

rm -rf build
mkdir build
cd build

gitbook pdf ../../ "$name.pdf"
gitbook epub ../../ "$name.epub"
gitbook mobi ../../ "$name.mobi"
