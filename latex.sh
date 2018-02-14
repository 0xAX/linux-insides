#!/bin/bash
rm -r build 
mkdir build
for D in *; do
    if [ -d "${D}" ] && [ "${D}" != "build" ]
    then
        echo "Converting $D . . ."
        pandoc ./$D/README.md ./$D/linux-*.md -o build/$D.tex --template default
    fi
done

cd ./build
for f in *.tex
do
    pdflatex -interaction=nonstopmode $f 
done

cd ../
pandoc README.md SUMMARY.md CONTRIBUTING.md CONTRIBUTORS.md \
   -o ./build/Preface.tex --template default

pdfunite ./build/*.pdf LinuxKernelInsides.pdf

