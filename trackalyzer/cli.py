import sys

import gpxpy, gpxpy.gpx, gpxpy.geo

# time window to calculate average speed in seconds.
ROLLING_AVERAGE_TIME_SECONDS = 90

# number of points of new state before switching to new state.
THRESHOLD_STATE_TRANSITION_POINTS = 2

# extrema for stationary speed in meters per second.
EXTREMA_RESTING_MPS = (0.0, 0.5)

# extrema for walking speed in meters per second.
# https://en.wikipedia.org/wiki/Preferred_walking_speed
EXTREMA_WALKING_MPS = (0.5, 2.5)

# extrema for cycling speed in meters per second.
# https://en.wikipedia.org/wiki/Bicycle_performance#Energy_efficiency
EXTREMA_CYCLING_MPS = (16000.0 / 60, 24000.0 / 60)

# extrema for driving/motorcycling/etc.
EXTREMA_MOTORING_MPS = (30000.0 / 60, 120000 / 60)

# travel states understood by the algorithm.
STATE_RESTING = 0
STATE_WALKING = 1
STATE_CYCLING = 2
STATE_MOTORING = 3
STATE_MOVING = 4


def calculate_delta(points):
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


def speed_matches(extrema, speed):
    return speed >= extrema[0] and speed <= extrema[1]


def calculate_state(speed):
    if speed_matches(EXTREMA_RESTING_MPS, speed):
        return STATE_RESTING

    if speed_matches(EXTREMA_WALKING_MPS, speed):
        return STATE_WALKING

    #if speed_matches(EXTREMA_CYCLING_MPS, speed):
    #    return STATE_CYCLING

    return STATE_MOVING


def state_resting(state):
    return state == STATE_RESTING


def state_active(state):
    return not state_resting(state)


def state_name(state):
    if state == STATE_RESTING:
        return "resting"
    if state == STATE_WALKING:
        return "walking"
    if state == STATE_CYCLING:
        return "cycling"
    if state == STATE_MOVING:
        return "moving"


def run():
    gpxpath = sys.argv[1]

    # read in and parse the GPX file provided on command line.
    with open(gpxpath, 'r') as fd:
        gpx = gpxpy.parse(fd)

    # set our initial conditions.
    current_state = STATE_RESTING
    current_state_points = []
    next_state_countdown = THRESHOLD_STATE_TRANSITION_POINTS

    analysis_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                # add points to ringbuffer and current state buffer.
                analysis_points.append(point)
                current_state_points.append(point)

                analysis_distance, analysis_duration, analysis_speed = calculate_delta(analysis_points)

                # buffer points until we've reached our minimum duration.
                if analysis_duration < ROLLING_AVERAGE_TIME_SECONDS:
                    continue

                prev_point = current_state_points[-1]
                first_point = current_state_points[0]

                # prepare format strings for point output.
                first_point_s = "(%s, %s)" % (first_point.latitude, first_point.longitude)
                prev_point_s = "(%s, %s)" % (prev_point.latitude, prev_point.longitude)
                point_s = "(%s, %s)" % (point.latitude, point.longitude)

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
                                  "Points:", len(current_state_points), "Jitter:", int(resting_distance), "meters.")
                            print()

                        # switch to the new state, reset transition counter, and populate
                        # the current state points from analysis buffer for continuity.
                        current_state = next_state
                        current_state_points = analysis_points.copy()
                        next_state_countdown = THRESHOLD_STATE_TRANSITION_POINTS

                # if we've reached this point, we can drop the oldest point.
                analysis_points.pop(0)

