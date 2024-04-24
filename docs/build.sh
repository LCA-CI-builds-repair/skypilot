## Remove the existing build directory
rm -rf build

# Generate HTML documentation
make htmlin/bash

rm -rf build docs
make html
