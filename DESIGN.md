# DESIGN

## input

key pieces of information from GPX:

- time (UTC)
- location (latitude, longitude)
- speed (m/s)
- accuracy (HDOP)

## processes

1. state: identify active -> passive, passive -> active, active -> active
2. cluster: identify all points in current state, find the center
3. identify: reverse geocode to an address or point of interest
4. finalize: deduplication and cleanup

### state

keep a running average of the current speed, using a ringbuffer.

keep all relevant points for current state in an elastic buffer.

prevent sloshing back and forth between states with overlapping extrema.

flush the buffer when a state transition occurs.

caveat: if there is a long interval between points, calculated speed may be unreliable.

### cluster

identify the center point from a set of points.

take the mean of latitudes over the mean of longitudes.

### identify

identify a point of interest with Overpass Turbo using the center coordinate.

### finalize

currently no post processing is done
