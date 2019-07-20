# Create a base docker container that will run FSL's SIENA command

FROM flywheel/fsl-base:5.0_neurodeb
MAINTAINER Flywheel <support@flywheel.io>


# Install python package dependencies
COPY requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt

# Make directory for flywheel spec (v0)
ENV FLYWHEEL /flywheel/v0
RUN mkdir -p ${FLYWHEEL}
COPY run.py ${FLYWHEEL}/run.py
RUN chmod +x ${FLYWHEEL}/run.py
COPY manifest.json ${FLYWHEEL}/manifest.json
