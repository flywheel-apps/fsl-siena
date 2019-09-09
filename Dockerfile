# Create a base docker container that will run FSL's SIENA command

FROM flywheel/fsl-siena:1.0.1_5.0
MAINTAINER Flywheel <support@flywheel.io>

# Copy optiBET scripts
ADD https://ucla.box.com/shared/static/2pzgonibfs413ec8adlikej7oi2lxbhr.sh /usr/local/bin/optiBET.sh
RUN chmod +x /usr/local/bin/optiBET.sh
COPY siena_optibet /usr/lib/fsl/5.0/siena_optibet
RUN chmod +x /usr/lib/fsl/5.0/siena_optibet
COPY sienax_optibet /usr/lib/fsl/5.0/sienax_optibet
RUN chmod +x /usr/lib/fsl/5.0/siena_optibet

# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
COPY siena_optibet ${FLYWHEEL}/siena_optibet
COPY sienax_optibet ${FLYWHEEL}/sienax_optibet
COPY manifest.json ${FLYWHEEL}/manifest.json

