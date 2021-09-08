import trackalyzer

import sys

import click
import gpxpy


@click.group()
@click.option("--poi/--no-poi", default=False, help="calculate points of interest")
@click.option("--verbose/--no-verbose", default=False, help="increased verbosity")
@click.option("--analysis-duration", default=trackalyzer.ROLLING_AVERAGE_TIME_SECONDS,
              help="time period to use for speed calculation (seconds)")
@click.pass_context
def run(ctx, poi, verbose, analysis_duration):
    ctx.obj = {
        "poi": poi,
        "verbose": verbose,
        "analysis_duration": analysis_duration,
    }


@run.command()
@click.argument("path")
@click.pass_context
def print(ctx, path):
    gpx = trackalyzer.load_gpx_path(path)
    trackalyzer.print_location_history(gpx, ctx.obj)


#@run.command()
#@click.argument("path")
#@click.pass_context
#def create(ctx, path):
#    gpx = trackalyzer.load_gpx_path(path)
#    print(trackalyzer.make_location_history_gpx(gpx).to_xml())


@run.command()
@click.option("--trace/--no-trace", default=False, help="include all intermediate points")
@click.option("--cluster/--no-cluster", default=False, help="include clustered resting points")
@click.option("--output", default="./folium-render.html", help="path to render output to")
@click.argument("path")
@click.pass_context
def render(ctx, trace, cluster, output, path):
    gpx = trackalyzer.load_gpx_path(path)
    trackalyzer.render_location_history(gpx, trace, cluster, output, ctx.obj)
