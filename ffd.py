#!/usr/bin/env python
#
# ffd.py
#
# Created by Joryl Calizo on 09/12/2015.
# Copyright (c) 2015. All rights reserved.
#

"""
Main entry point to FFD engine.
"""

import os
import argparse
import yaml
import pandas as pd
import sys
import itertools as it
import pprint as pp
import progressbar

# standardize data frame
def read_fanduel_salaries(filename):
    df = pd.read_csv(filename, usecols=["Salary", "First Name", "Last Name", "Position"])

    # use standard column names
    df["Name"] = df["First Name"] + " " + df["Last Name"]
    df.pop("First Name")
    df.pop("Last Name")
    return df

def read_fanduel_player_data(filename, player_info="all"):
    cols = ["First Name", "Last Name"]
    if player_info == "all":
        player_info = ["Base Projection", "Injury Status"]

    # requested parameters don't always match column names
    if "Base Projection" in player_info:
        cols.append("FPPG")

    if "Injury Status" in player_info:
        cols.append("Injury Indicator")

    # read .csv file
    df = pd.read_csv(filename, usecols=cols)

    # use standard column names
    df["Name"] = df["First Name"] + " " + df["Last Name"]
    df.pop("First Name")
    df.pop("Last Name")

    # some parameters are optional. just catch exceptions for parameters that
    # weren't requested - it's simpler than checking player_info
    try:
        df["Base Projection"] = df["FPPG"]
        df.pop("FPPG")
    except:
        pass

    try:
        df["Injury Status"] = df["Injury Indicator"]
        df.pop("Injury Indicator")
    except:
        pass

    return df

def compute_derived_data(df):
    # this function is called multiple times. some columns don't exist on the
    # first pass, so let's just cheat and catch exceptions for now
    try:
        df["Base PPD"] = df["Base Projection"] / df["Salary"]
    except:
        pass

    try:
        df["Modeled PPD"] = df["Modeled Projection"] / df["Salary"]
    except:
        pass

    return df

def tune_player_projections(df, models=None):
    # todo: define input format for models once they're actually supported

    # still in development. passthrough for now.
    df["Modeled Projection"] = df["Base Projection"]
    return df

def tune_lineup_projections(df, models=None):
    # todo: define input format for models once they're actually supported

    # still in development. passthrough for now.
    df["Total Modeled Projection"] = df["Total Base Projection"]
    return df

def anal_lineups(data_df, lineup_df, fom, anal_info):
    # .yaml file should contain a list of parameters to compute
    # analysis is only done on the "best" lineups
    # assumes figure-of-merit input parameter is a column name
    # todo: should there be a nested sort to handle ties?
    # todo: analyze base projections and model projections independently
    lineup_df.sort(fom, ascending=False, inplace=True)
    trimmed_df = lineup_df.head(anal_info["max_lineups"])

    stats_df = pd.DataFrame()
    # build a dictionary of statistics for each player as key, then generate
    # data frame with one player per row
    stats_dict = {}

    # compute frequency for each player
    # todo: don't hardcode position list
    for pos in ["QB_1", "RB_1", "RB_2", "WR_1", "WR_2", "WR_3", "TE_1", "K_1", "D_1"]:
        hist = trimmed_df[pos].value_counts().to_dict()
        for player in hist:
            # lazy!
            # todo: seriously, use classes.
            if player not in stats_dict:
                stats_dict[player] = {}
                stats_dict[player]["position"] = pos.split("_")[0]

            # some players can show up in different positions (e.g., WR1, WR2)
            # use count as normalization factor. this is relative frequency,
            # not absolute frequency
            if "frequency" not in stats_dict[player]:
                stats_dict[player]["frequency"] = hist[player] / float(anal_info["max_lineups"])
            else:
                stats_dict[player]["frequency"] += hist[player] / float(anal_info["max_lineups"])

    # for each player (key), reformat dictionary to be data frame compliant
    # todo: a custom class can override these transform methods
    for player in stats_dict:
        player_info = {
            "Name": player
        }
        for stat in stats_dict[player]:
            player_info[stat] = stats_dict[player][stat]
        stats_df = stats_df.append(player_info, ignore_index=True)

    return {"trimmed_df": trimmed_df, "stats_df": stats_df}

def report_data(data_df, anal_res, fom, anal_info):
    stats_df = anal_res["stats_df"]
    trimmed_df = (anal_res["trimmed_df"]).sort(fom, ascending=False)
    # todo: don't hardcode positions
    positions = ["QB", "RB", "WR", "TE", "K", "D"]

    print(stats_df)

    print("\n\nRelative frequencies (based on top " + str(anal_info["max_lineups"]) + "lineups):")
    stats_df.sort("frequency", ascending=False, inplace=True)
    for pos in positions:
        print(pos + ":")
        df = stats_df[stats_df["position"] == pos]
        for player_info in df.to_dict("records"):
            print("\t" + player_info["Name"] + ": " +
                str(player_info["frequency"]))

    trimmed_df = trimmed_df.head(anal_info["top_lineups"])
    print("\n\nTop " + str(anal_info["top_lineups"]) + " lineups:")
    print(trimmed_df)

# filter data
# todo: there's a better way to do this. but fuck it
def filter_df(df, filters):
    # is there a better way to initialize this?
    first = 1
    for pos in filters:
        # min/max, PPG, PPD filters are always applied
        pos_filter = ((df.Position == pos) & (df.Salary >= filters[pos]["min"]) & (df.Salary <= filters[pos]["max"]))
        pos_filter &= (df["Base Projection"] >= filters[pos]["output"]["min_base_projected"])
        pos_filter &= (df["Base PPD"] >= filters[pos]["output"]["min_base_ppd"])

        # check optional filters
        if filters[pos]["exclude_injury"]["probable"] == 1:
            pos_filter &= (df["Injury Status"] != "P")
        if filters[pos]["exclude_injury"]["questionable"] == 1:
            pos_filter &= (df["Injury Status"] != "Q")
        if filters[pos]["exclude_injury"]["out"] == 1:
            pos_filter &= (df["Injury Status"] != "O")
        if filters[pos]["exclude_injury"]["injured_reserve"] == 1:
            pos_filter &= (df["Injury Status"] != "IR")

        # filtered_idx is the OR of all filters
        if first == 1:
            filtered_idx = pos_filter
            first = 0
        else:
            filtered_idx |= pos_filter

        # todo: only for testing
        print("\n\nEligible " + pos + "(s):")
        print(df[pos_filter])

    # todo: only for testing
    # print("\n\nFiltering out the following players:")
    # print(df.Name[-filtered_idx])

    return df[filtered_idx]

def verify_lineup(df, rules, lineup):
    lineup_dict = {
        "QB_1": lineup[0][0],
        "RB_1": lineup[1][0],
        "RB_2": lineup[1][1],
        "WR_1": lineup[2][0],
        "WR_2": lineup[2][1],
        "WR_3": lineup[2][2],
        "TE_1": lineup[3][0],
        "K_1": lineup[4][0],
        "D_1": lineup[5][0],
        "Total Salary": 0,
        "Total Base Projection": 0
    }

    valid_lineup = 1
    for name in lineup_dict:
        if name == "Total Salary" or name == "Total Base Projection":
            continue
        player_salary = df[df["Name"] == lineup_dict[name]].Salary
        lineup_dict["Total Salary"] += player_salary.values[0]
        player_base_projection = df[df["Name"] == lineup_dict[name]]["Base Projection"]
        lineup_dict["Total Base Projection"] += player_base_projection.values[0]
        # todo: break immediately if over salary cap
        if lineup_dict["Total Salary"] > rules["cap"]:
            valid_lineup = 0
            break

    if valid_lineup == 1:
        # create data frame with dummy index (ignored by concat)
        result = pd.DataFrame(lineup_dict, index=[0])
    else:
        result = None

    verify_lineup.lineup_count += 1
    verify_lineup.bar.update(verify_lineup.lineup_count)

    return result

# build lineups
def gen_lineup_df(df, rules):
    combos = {}
    lineup_info = rules["lineup"]
    lineup_df = pd.DataFrame()
    for pos in lineup_info:
        for pos_num in range(lineup_info[pos]["count"]):
            lineup_df[pos + "_" + str(pos_num + 1)] = None
        combos[pos] = list(it.combinations(
            df[df.Position == pos].Name, lineup_info[pos]["count"])
        )
        #print(pos + " count: " + str(len(df[df.Position == pos])))
        #print(pos + " combo count: " + str(len(combos[pos])))

    # todo: don't hardcode this
    lineups = list(it.product(
        combos["QB"],
        combos["RB"],
        combos["WR"],
        combos["TE"],
        combos["K"],
        combos["D"])
    )

    # determine which lineups are valid
    # use progress bar for real time status feedback
    # lineup_count: number of lineups considered
    verify_lineup.lineup_count = 0
    verify_lineup.bar = progressbar.ProgressBar(
        maxval=len(lineups),
        widgets=[
            "Building list of valid lineups ",
            progressbar.Bar('=', '[', ']'),
            " ",
            progressbar.FormatLabel('%(value)d of %(max)d')
        ]
    )
    print("\n")
    verify_lineup.bar.start()
    frames = [ verify_lineup(df, rules, lineup) for lineup in lineups ]
    verify_lineup.bar.finish()

    # concatenate all lineup data (None's are silently ignored)
    lineup_df = pd.concat(frames, ignore_index=True)

    return lineup_df

if __name__ == "__main__":
    # parse args
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-y", "--config_filename",
        default="" + os.path.dirname(__file__) + "/config/ff.yaml",
        help="Path to .yaml file containing configuration details."
    )
    opts = vars(parser.parse_args())

    # read configuration info
    config_info = yaml.load(file(opts["config_filename"], "r"))

    # todo: only for testing
    # pp.pprint(config_info)

    # import salary data
    # todo: make an input class
    # todo: will we need to support anything else?
    if config_info["input"]["salaries"]["type"] == "fanduel":
        salary_df = read_fanduel_salaries(
            config_info["input"]["salaries"]["filename"]
        )
    else:
        print("Unsupported salary file.")
        sys.exit(0)

    # import projections
    # todo: make an input class
    # todo: add support for other sources
    # todo: handle multiple sources simultaneously. maybe have an optional
    # parameter specifying which columns to use from the given database
    if config_info["input"]["projections"]["type"] == "fanduel":
        projections_df = read_fanduel_player_data(
            config_info["input"]["projections"]["filename"]
        )
    else:
        print("Unsupported projections file.")
        sys.exit(0)

    # merge data frames
    data_df = pd.merge(salary_df, projections_df)

    # generate other columns
    data_df = compute_derived_data(data_df)

    # filter data frame
    # this is a pre-filter to remove "useless" entries (e.g., players on IR,
    # third string QBs, etc.)
    # really, this is just used to trim down the dataset to be more manageable.
    data_df = filter_df(data_df, config_info["filters"])

    # apply per-player models
    # todo: models should be read from an input .yaml file, but currently, none
    # actually exist. so the raw and tuned projections are identical
    data_df = tune_player_projections(data_df, config_info["models"]["single"])

    # generate other columns (called again to generate any columns that are
    # dependent on the models
    data_df = compute_derived_data(data_df)

    # build permutations, generate list of "valid" lineups
    # todo: currently, a "valid" lineup is only defined as a team that is under
    # the salary cap.
    lineup_df = gen_lineup_df(data_df, config_info["rules"])

    # apply per-lineup models
    # todo: not yet implemented
    lineup_df = tune_lineup_projections(lineup_df, config_info["models"]["team"])

    # anal-eyes top lineups
    res = anal_lineups(data_df, lineup_df, "Total Modeled Projection",
        config_info["anal"])

    # report anal-isis
    report_data(data_df, res, "Total Modeled Projection", config_info["anal"])

    # we should really just report the sorted and trimmed lineup list
    lineup_df = res["trimmed_df"]
    lineup_df.to_csv("/tmp/poop.csv", index=False)


