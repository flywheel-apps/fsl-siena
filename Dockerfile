# Create a base docker container that will run FSL's SIENA command

FROM flywheel/fsl-siena:1.0.0_5.0
MAINTAINER Flywheel <support@flywheel.io>

# Copy optiBET scripts
COPY optiBET.sh /usr/local/bin/optiBET.sh
RUN chmod +x /usr/local/bin/optiBET.sh
COPY siena_optibet /usr/lib/fsl/5.0/siena_optibet
RUN chmod +x /usr/lib/fsl/5.0/siena_optibet
COPY sienax_optibet /usr/lib/fsl/5.0/sienax_optibet
RUN chmod +x /usr/lib/fsl/5.0/siena_optibet

# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
RUN mkdir -p ${FLYWHEEL}
COPY run.py ${FLYWHEEL}/run.py
COPY manifest.json ${FLYWHEEL}/manifest.json

