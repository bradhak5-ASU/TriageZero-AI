# Runs the NovaCart Playwright suite against the deployed shop and reports
# failures to TriageZero.
#
# The Playwright base image already contains the browsers and their system
# libraries. Installing them at container start instead would add minutes to
# every scheduled run and depend on the network staying up.
FROM mcr.microsoft.com/playwright:v1.46.1-jammy

WORKDIR /suite

# The suite is staged here by deploy/build-runner.sh from the read-only
# NovaCart repository; nothing there is modified.
COPY suite/package*.json ./
RUN npm ci --omit=optional || npm install
COPY suite/ ./

COPY run.sh /run.sh
RUN chmod +x /run.sh
ENTRYPOINT ["/run.sh"]
