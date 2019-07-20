# fsl-siena
A Flywheel gear for running FSL's SIENA. 

SIENA is a package for both single-time-point ("cross-sectional") and 
two-time-point ("longitudinal") analysis of brain change, in particular, the estimation of atrophy 
(volumetric loss of brain tissue). SIENA has been used in many clinical studies.

Siena estimates percentage brain volume change (PBVC) betweem two input images, taken of the same subject, at different 
points in time. It calls a series of FSL programs to strip the non-brain tissue from the two images, register the two 
brains (under the constraint that the skulls are used to hold the scaling constant during the registration) and analyse 
the brain change between the two time points. It is also possible to project the voxelwise atrophy measures into 
standard space in a way that allows for multi-subject voxelwise statistical testing. An extension for ventricular 
analysis is provided in FSL5.

Additional documentation and usage can be found at [FMRIB](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/SIENA).