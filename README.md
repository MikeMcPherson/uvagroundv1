# UVaGroundStation
Software for the University of Virginia satellite ground station

There will be several iterations: 
(1) A very rudimentary test ("usrxtx"), two command-line programs that just exercise the Gnu Radio flowgraph.
(2) The development and testing version ("ground"), written in Python with PyGObjects, manually operated 
    to allow the spacecraft software team to test their software.  It supports the UVa TM and TC packet 
    structures, and can conduct full two-way exchanges with the spacecraft.  This *could* be the ground 
    station (along with predict for tracking and Doppler), if worse came to worst.
(3) The production version, based on NASA's OpenMCT, written in JavaScript with Node.JS and Angular.JS.
    Very much a work in progress.
