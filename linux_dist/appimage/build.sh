#!/bin/bash
set -Ceufox pipefail

docker build -t atlas-appimage .
docker run -e ATLAS_VERSION=$ATLAS_VERSION -v ./AppImageBuilder.yml:/build/AppImageBuilder.yml --rm --cap-add=SYS_ADMIN --device /dev/fuse --mount type=bind,source="$(pwd)",target=/build atlas-appimage
# volume required to run tests: -v /var/run/docker.sock:/var/run/docker.sock
