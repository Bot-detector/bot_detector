FROM ghcr.io/anomalyco/opencode:1.1.25

# 1. Install basic utilities
RUN apk add --no-cache \
    git \
    curl \
    wget \
    bash \
    vim

# 2. Create the opencode user and group with ID 1000
# -g 1000: Set Group ID
# -u 1000: Set User ID
# -D: Don't assign a password
# -G: Assign the user to the specified group
RUN addgroup -g 1000 opencode \
    && adduser -u 1000 -G opencode -D opencode

# 3. Create the directory and set ownership/permissions
RUN mkdir -p /opencode \
    && chown -R opencode:opencode /opencode \
    && chmod 755 /opencode

# 4. Set the working directory (optional but recommended)
WORKDIR /opencode

# 5. Switch to the non-root user
USER opencode

# The entrypoint from the base image (the 'opencode' binary) 
# will now run as the 'opencode' user.