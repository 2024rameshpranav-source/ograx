
MUMBAI MONSOON WATERLOGGING EARLY-WARNING PROTOTYPE
===================================================

WHAT THIS IS
------------
A rule-based rainfall screening prototype for 8 Mumbai locations.
It is NOT a trained or validated machine-learning model and does
not calculate a waterlogging probability.

FILES
-----
warning_engine.py
    Standalone Python screening engine.

mumbai_waterlogging_nowcast.csv
    Recent and forecast rainfall input, if available in this package.

CSV output files
    Historical data, location context, screening results and
    dashboard-ready exports.

RUNNING THE ENGINE
------------------
Install Python 3 and pandas:

    pip install pandas

Place warning_engine.py and mumbai_waterlogging_nowcast.csv in the
same directory, then run:

    python warning_engine.py

The default output is:
    mumbai_waterlogging_warning_engine.csv

IMPORTANT LIMITATIONS
---------------------
- Thresholds are experimental, not official flood-warning thresholds.
- Rainfall signals do not confirm that a road will flood.
- Reported hotspot evidence is incomplete and not a validated label.
- Waterlogging probabilities are intentionally left blank.
- Data freshness and forecast quality should be checked before use.
- Do not use this prototype as a public-safety warning system without
  appropriate validation and operational review.
