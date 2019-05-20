# UVaGroundStation
Software for the University of Virginia satellite ground station

There will be several iterations: 
* (V0) A very rudimentary test ("usrxtx"), two command-line programs that just exercise the Gnu Radio flowgraph.
* (V1, thie version in this repository) The development and testing version ("ground"), written in Python with PyGObjects, manually operated to allow the spacecraft software team to test their software.  It supports the UVa TM and TC packet structures, and can conduct full two-way exchanges with the spacecraft.  This *could* be the ground station (along with predict for tracking and Doppler), if worse came to worst.
* (V2) The production version, with Web interface, automation, and graphical interfaces.  Very much a work in progress.
