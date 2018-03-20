# latex.sh
# A script for converting Markdown files in each of the subdirectories into a unified PDF typeset in LaTeX. 
# Requires TexLive, Pandoc templates and pdfunite. Not necessary if you just want to read the PDF, only if you're compiling it yourself.

#!/bin/bash
rm -r build 
mkdir build
for D in $(ls ../); do
    if [ -d "../${D}" ]
    then
        echo "Converting $D . . ."
        pandoc ../$D/README.md ../$D/linux-*.md -o build/$D.tex --template default
    fi
done

cd ./build
for f in *.tex
do
    pdflatex -interaction=nonstopmode $f 
done

cd ../
pandoc ../README.md ../SUMMARY.md ../CONTRIBUTING.md ../contributors.md \
   -o ./build/Preface.tex --template default

pdfunite ./build/*.pdf LinuxKernelInsides.pdf
