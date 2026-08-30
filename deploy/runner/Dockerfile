# Runs the NovaCart Playwright suite against the deployed shop and reports
# failures to TriageZero.
#
# The Playwright base image already contains the browsers and their system
# libraries. Installing them at container start instead would add minutes to
# every scheduled run and depend on the network staying up.
# The browsers in this image must match the Playwright version the suite
# resolves to, or every test dies with "Executable doesn't exist". The suite
# declares a caret range, so that version moves on its own - it resolved to
# 1.62.1 while this image was pinned to 1.46.1. build-runner.sh reads the
# actual version out of the suite's lockfile and passes it in, so the image
# tracks the suite instead of a guess made at authoring time.
ARG PLAYWRIGHT_VERSION=1.46.1
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-jammy

# Named to match the suite's path in its own repository. Playwright reports
# test files relative to this directory, so a container-specific name like
# /suite would surface in every investigation as "suite/tests/..." - a path
# that does not exist in the project a reader would go looking in.
WORKDIR /playwright-tests

# The suite is staged here by deploy/build-runner.sh from the read-only
# NovaCart repository; nothing there is modified.
COPY suite/package*.json ./
RUN npm ci --omit=optional || npm install
COPY suite/ ./

COPY run.sh /run.sh
RUN chmod +x /run.sh
ENTRYPOINT ["/run.sh"]
