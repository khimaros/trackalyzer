import collections
import json
import time
import urllib.parse, urllib.request, urllib.error
import xml.etree

from typing import List, Tuple, Iterable

import folium
import gpxpy.gpx, gpxpy.geo


# time window to calculate average speed in seconds.
ROLLING_AVERAGE_TIME_SECONDS = 45

# number of points of new state before switching to new state.
THRESHOLD_STATE_TRANSITION_POINTS = 1

# extrema for stationary speed in meters per second.
EXTREMA_RESTING_MPS = (0.0, 0.2)

# extrema for walking speed in meters per second.
# https://en.wikipedia.org/wiki/Preferred_walking_speed
EXTREMA_WALKING_MPS = (0.2, 1.5)

# extrema for cycling speed in meters per second.
# https://en.wikipedia.org/wiki/Bicycle_performance#Energy_efficiency
EXTREMA_CYCLING_MPS = (1.5, 15)

# extrema for driving/motorcycling/etc.
EXTREMA_MOTORING_MPS = (30000.0 / 3600, 120000 / 3600)

# travel states understood by the algorithm.
STATE_RESTING = 0
STATE_WALKING = 1
STATE_CYCLING = 2
STATE_MOTORING = 3
STATE_MOVING = 4


LocationState = collections.namedtuple(
    "LocationState", ["current_state", "points", "next_state", "amenities"]
)


def calculate_delta(points: List[gpxpy.gpx.GPXTrackPoint]) -> Tuple[float, float, float]:
    prev_point = None
    total_distance = 0
    total_duration = 0

    for point in points:
        if prev_point:
            distance = point.distance_2d(prev_point)
            duration = point.time_difference(prev_point)
            total_distance += distance
            total_duration += duration
        prev_point = point

    if not total_duration:
        return total_distance, total_duration, 0

    average_speed = total_distance / total_duration

    return total_distance, total_duration, average_speed


def speed_matches(extrema: Tuple[float, float], speed: float) -> bool:
    return speed >= extrema[0] and speed <= extrema[1]


def calculate_state(speed: float) -> int:
    if speed_matches(EXTREMA_RESTING_MPS, speed):
        return STATE_RESTING
    if speed_matches(EXTREMA_WALKING_MPS, speed):
        return STATE_WALKING
    if speed_matches(EXTREMA_CYCLING_MPS, speed):
        return STATE_CYCLING

    return STATE_MOVING


def state_resting(state: int) -> bool:
    return state == STATE_RESTING


def state_active(state: int) -> bool:
    return not state_resting(state)


def state_name(state: int) -> str:
    if state == STATE_RESTING:
        return "resting"
    if state == STATE_WALKING:
        return "walking"
    if state == STATE_CYCLING:
        return "cycling"
    if state == STATE_MOVING:
        return "moving"


# TODO: return a GPXTrackPoint
def calculate_center(points: List[gpxpy.gpx.GPXTrackPoint]) -> Tuple[int, int]:
    latitudes = []
    longitudes = []
    for point in points:
        latitudes.append(point.latitude)
        longitudes.append(point.longitude)

    center_coord = (
        sum(latitudes) / len(latitudes),
        sum(longitudes) / len(longitudes)
    )

    return center_coord


def calculate_center_point(points: List[gpxpy.gpx.GPXTrackPoint]) -> gpxpy.gpx.GPXTrackPoint:
    center_coord = calculate_center(points)

    center_point = gpxpy.gpx.GPXTrackPoint(
        center_coord[0], center_coord[1],
        time=points[0].time)

    return center_point


# TODO: accept GXPTrackPoint
def query_osm_address(center):
    pass


def query_overpass_around(points, diameter=25, max_query_coords=10):
    potential_pois = []

    coords = []
    for point in points:
        coords.append("%f,%f" % (point.latitude, point.longitude))

    oparound = "%d,%s" % (diameter, ",".join(coords[:max_query_coords]))
    opdata = """
        [out:json];
        (
            way[amenity](around:%s);
            node[amenity](around:%s);
        );
        (._;>;);
        out body;
    """ % (oparound, oparound)
    opurl = "https://overpass-api.de/api/interpreter?data=%s" % urllib.parse.quote(opdata)

    data = None
    while not data:
        try:
            with urllib.request.urlopen(opurl) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            time.sleep(2)

    for el in data["elements"]:
        if not "tags" in el:
            continue
        if "name" in el["tags"]:
            potential_pois.append(el["tags"]["name"])
        if "operator" in el["tags"]:
            potential_pois.append(el["tags"]["operator"])

    return potential_pois


def make_osm_link(point: gpxpy.gpx.GPXTrackPoint) -> str:
    coord = point.latitude, point.longitude
    return "https://www.openstreetmap.org/?mlat=%f&mlon=%f#map=19/%f/%f" % (
            coord + coord)


def load_gpx_path(path: str) -> gpxpy.gpx.GPXTrack:
    # read in and parse the GPX file provided on command line.
    with open(path, 'r') as fd:
        gpx = gpxpy.parse(fd)

    return gpx


def track_point_speed(point):
    for ext in point.extensions:
        if ext.tag == '{https://osmand.net}speed':
            return float(ext.text)
    return None


def generate_location_history(gpx, params=None) -> Iterable[LocationState]:
    if not params:
        params = {
            "verbose": False,
            "poi": False,
            "analysis_duration": ROLLING_AVERAGE_TIME_SECONDS,
        }

    # set our initial conditions.
    current_state = STATE_RESTING
    current_state_points = []
    next_state_countdown = THRESHOLD_STATE_TRANSITION_POINTS

    if params["verbose"]:
        print("---", state_name(current_state))

    analysis_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                # add points to ringbuffer and current state buffer.
                analysis_points.append(point)
                current_state_points.append(point)

                analysis_distance, analysis_duration, analysis_speed = calculate_delta(analysis_points)

                # buffer points until we've reached our minimum duration.
                if analysis_duration < params["analysis_duration"]:
                    continue

                next_state = calculate_state(analysis_speed)
                # if the next state is the same as current, reset the transition counter.
                if next_state == current_state:
                    next_state_countdown = THRESHOLD_STATE_TRANSITION_POINTS
                # if we've slipped into a new state, start the transition countdown.
                else:
                    # if we still have some transition buffer left, take some away.
                    if next_state_countdown > 0:
                        next_state_countdown -= 1
                    # if we have reached the state transition threshold:
                    else:
                        relevant_points = current_state_points[:-THRESHOLD_STATE_TRANSITION_POINTS]
                        if params["verbose"]:
                            for state_point in relevant_points:
                                print("   ", state_point, track_point_speed(state_point), state_point.horizontal_dilution)
                            print("---", state_name(current_state), "=>", state_name(next_state),  point)

                        potential_pois = None
                        if params["poi"] and state_resting(current_state):
                            potential_pois = query_overpass_around(current_state_points)

                        yield LocationState(
                            current_state,
                            relevant_points,
                            next_state,
                            potential_pois,
                        )

                        # switch to the new state, reset transition counter, and populate
                        # the current state points from analysis buffer for continuity.
                        current_state = next_state
                        current_state_points = analysis_points.copy()
                        next_state_countdown = THRESHOLD_STATE_TRANSITION_POINTS

                # if we've reached this point, we can drop the oldest point.
                analysis_points.pop(0)


def make_location_history_gpx(gpx):
    hist_gpx = gpxpy.gpx.GPX()
    hist_track = gpxpy.gpx.GPXTrack()
    hist_gpx.tracks.append(hist_track)
    hist_segment = gpxpy.gpx.GPXTrackSegment()
    hist_track.segments.append(hist_segment)

    for current_state, current_state_points, _, _ in generate_location_history(gpx):
        if state_resting(current_state):
            center_point = calculate_center_point(current_state_points)

            osmlink = make_osm_link(center_point)

            hist_point = gpxpy.gpx.GPXTrackPoint(
                center_point.latitude, center_point.longitude,
                time=current_state_points[0].time)

            _, resting_duration, _ = calculate_delta(current_state_points)

            hist_visit = xml.etree.ElementTree.Element("{trackalyzer}visit")
            hist_visit.attrib["DurationSeconds"] = resting_duration
            hist_visit.attrib["URL"] = osmlink
            hist_point.extensions.append(hist_visit)
            hist_segment.points.append(hist_point)

    return hist_gpx


def render_location_history(gpx, trace=False, cluster=False, output=None, params=None):
    first_point = gpx.tracks[0].segments[0].points[0]

    fmap = folium.Map(
        location=[first_point.latitude, first_point.longitude],
        tiles="OpenStreetMap", zoom_start=15)

    for current_state, current_state_points, _, potential_pois in generate_location_history(gpx, params):
        if (trace and state_active(current_state)) or (cluster and state_resting(current_state)):
            color = "green" if state_active(current_state) else "red"
            for state_point in current_state_points:
                folium.Marker(
                    location=[state_point.latitude, state_point.longitude],
                    icon=folium.Icon(color=color),
                ).add_to(fmap)

        if not state_resting(current_state):
            continue

        center_point = calculate_center_point(current_state_points)
        center_coord = center_point.latitude, center_point.longitude

        folium.Marker(
            location=center_coord,
            popup=potential_pois or center_point.time.astimezone(), icon=folium.Icon(color="black"),
        ).add_to(fmap)

    fmap.save(output)


def print_location_history(gpx, params=None):
    for current_state, current_state_points, next_state, potential_pois in generate_location_history(gpx, params):
        point = current_state_points[-1]
        first_point = current_state_points[0]

        # prepare format strings for point output.
        first_point_s = "(%s, %s)" % (first_point.latitude, first_point.longitude)
        point_s = "(%s, %s)" % (point.latitude, point.longitude)

        # anytime we change to a new active state, print some details.
        if state_active(current_state):
            moving_distance, moving_duration, moving_speed = calculate_delta(current_state_points)
            print("Traveled", moving_distance, "meters in", moving_duration,
                    "seconds.", "Speed:", moving_speed, "m/s.", "State:", state_name(current_state))

        # if we move between active and resting states, print arrival/departure information.
        if state_active(current_state) and state_resting(next_state):
            print()
            print("Arrived at", point_s, "at", point.time.astimezone())
        elif state_resting(current_state) and state_active(next_state):
            resting_distance, resting_duration, resting_speed = calculate_delta(current_state_points)
            print("Departed", first_point_s, "at", point.time.astimezone(), "after", resting_duration, "seconds.",
                    "Points:", len(current_state_points), ". Jitter:", int(resting_distance), "meters.")
            center_point = calculate_center_point(current_state_points)
            center_coord = center_point.latitude, center_point.longitude
            osmlink = "https://www.openstreetmap.org/?mlat=%f&mlon=%f#map=19/%f/%f" % (
                    center_coord + center_coord)
            print("Center Lat/Lon: %f, %f -- %s" % (center_coord[0], center_coord[1], osmlink))
            print("Potential POIs:", potential_pois)
            print()