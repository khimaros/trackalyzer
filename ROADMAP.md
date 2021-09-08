# ROADMAP

## backlog

```
[ ] improve resting/active state transition heuristic
    [ ] utilize explicit speed data from GPX file
    [ ] create a fence when resting and change state upon exit
    [ ] use OSM building data
    [ ] separate extrema thresholds for rising vs. falling speed
[ ] improve clustering heuristic
    [ ] utilize HDOP data when calculating center
[ ] fine-tune active state transitions (cycling, motoring, etc.)
[ ] make folium an optional dependency
[ ] fall back to Nominatum address if no POI found
[ ] de-duplicate poi within a particular time interval
```

## complete

```
[x] add auto-retry for HTTP 429 responses from Overpass API
[x] resolve resting locations to points of interest
[x] identify basic state transitions (resting, walking, moving)
[x] batch points by average speed using a configurable analysis window
```
