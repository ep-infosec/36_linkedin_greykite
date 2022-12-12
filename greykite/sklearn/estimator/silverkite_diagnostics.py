#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# original author: Sayan Patra
"""Silverkite plotting functions."""
import warnings
from typing import Type

import numpy as np
import pandas as pd
from plotly import graph_objects as go
from plotly.subplots import make_subplots

from greykite.algo.changepoint.adalasso.changepoints_utils import get_trend_changepoint_dates_from_cols
from greykite.algo.common.model_summary import ModelSummary
from greykite.algo.forecast.silverkite.constants.silverkite_component import SilverkiteComponentsEnum
from greykite.algo.forecast.silverkite.constants.silverkite_component import SilverkiteComponentsEnumMixin
from greykite.algo.forecast.silverkite.constants.silverkite_constant import default_silverkite_constant
from greykite.common import constants as cst
from greykite.common.python_utils import get_pattern_cols
from greykite.common.viz.timeseries_plotting import add_groupby_column
from greykite.common.viz.timeseries_plotting import grouping_evaluation


class SilverkiteDiagnostics:
    """Provides various plotting functions for the model generated by the Silverkite forecast algorithms.

    Attributes
    ----------
    _silverkite_components_enum : Type[SilverkiteComponentsEnum]
        The constants for plotting the silverkite components.
    model_dict : `dict` or None
        A dict with fitted model and its attributes.
        The output of `~greykite.algo.forecast.silverkite.forecast_silverkite.SilverkiteForecast.forecast`.
    pred_category : `dict` or None
        A dictionary with keys being the predictor category and
        values being the predictors belonging to the category.
        For details, see
        `~greykite.sklearn.estimator.base_silverkite_estimator.BaseSilverkiteEstimator.pred_category`.
    time_col : str
        Name of input data time column
    value_col : str
        Name of input data value column
    components : `dict` or None
        Components of the ``SilverkiteEstimator`` model. Set by ``self.plot_components``.
        For details about the possible key values see
        `~greykite.sklearn.estimator.silverkite_diagnostics.SilverkiteDiagnostics.get_silverkite_components`.
        Not available for ``random forest`` and ``gradient boosting`` methods and
        set to the default value `None`.
    model_summary : `class` or `None`
        The `~greykite.algo.common.model_summary.ModelSummary` class.
    """
    def __init__(
            self,
            constants: SilverkiteComponentsEnumMixin = default_silverkite_constant):
        self._silverkite_components_enum: Type[SilverkiteComponentsEnum] = constants.get_silverkite_components_enum()
        self.pred_category = None
        self.time_col = None
        self.value_col = None
        self.components = None
        self.model_summary = None

    def set_params(self, pred_category, time_col, value_col):
        """
        Set the various params after the model has been created.

        Parameters
        ----------
        pred_category : `dict` or None
            A dictionary with keys being the predictor category and
            values being the predictors belonging to the category.
            For details, see `~greykite.sklearn.estimator.base_silverkite_estimator.BaseSilverkiteEstimator.pred_category`.
        time_col: `str`
            Time column name in the data frame.
        value_col: `str`
            Value column name in the data frame.
        """
        self.pred_category = pred_category
        self.time_col = time_col
        self.value_col = value_col

    def summary(self, model_dict, max_colwidth=20) -> ModelSummary:
        """Creates the model summary for the given model

        Parameters
        ----------
        model_dict : `dict` or None
            A dict with fitted model and its attributes.
        max_colwidth : `int`
            The maximum length for predictors to be shown in their original name.
            If the maximum length of predictors exceeds this parameter, all
            predictors name will be suppressed and only indices are shown.

        Returns
        -------
            model_summary: `ModelSummary`
            The model summary for this model. See `~greykite.algo.common.model_summary.ModelSummary`
        """

        if model_dict is not None:
            # tree models do not have beta
            self.model_summary = ModelSummary(
                x=model_dict["x_mat"].values,
                y=model_dict["y"].values,
                pred_cols=list(model_dict["x_mat"].columns),
                pred_category=self.pred_category,
                fit_algorithm=model_dict["fit_algorithm"],
                ml_model=model_dict["ml_model"],
                max_colwidth=max_colwidth)
        else:
            self.model_summary = None
        return self.model_summary

    def plot_components(self, model_dict, names=None, title=None):
        """Class method to plot the components of a ``Silverkite`` model on the dataset passed to ``fit``.

        Parameters
        ----------
        model_dict : `dict` or None
            A dict with fitted model and its attributes.
        names: `list` [`str`], default `None`
            Names of the components to be plotted e.g. names = ["trend", "DAILY_SEASONALITY"].
            See `~greykite.sklearn.estimator.silverkite_diagnostics.get_silverkite_components`
            for the full list of valid names.
            If `None`, all the available components are plotted.
        title: `str`, optional, default `None`
            Title of the plot. If `None`, default title is "Component plot".

        Returns
        -------
        fig: `plotly.graph_objects.Figure`
            Figure plotting components against appropriate time scale.
        """
        if model_dict is None:
            raise NotImplementedError("Call `self.set_params` before calling `plot_components`.")

        # recomputes `self.components` every time in case model was refit
        if not hasattr(model_dict["ml_model"], "coef_"):
            raise NotImplementedError("Component plot has only been implemented for additive linear models.")
        else:
            # Computes components for the training observations used to fit the model.
            # Observations with NAs that are dropped when fitting are not included.
            x_mat = model_dict["x_mat"]
            ml_model_coef = model_dict["ml_model"].coef_
            ml_model_intercept = model_dict["ml_model"].intercept_
            data_len = len(x_mat)
            ml_cols = list(x_mat.columns)

            x_mat_weighted = ml_model_coef * x_mat
            if ml_model_intercept:
                if "Intercept" in ml_cols:
                    x_mat_weighted["Intercept"] += np.repeat(ml_model_intercept, data_len)
                else:
                    x_mat_weighted["Intercept"] = np.repeat(ml_model_intercept, data_len)

            self.components = self.get_silverkite_components(
                df=model_dict["df_dropna"],
                time_col=self.time_col,
                value_col=self.value_col,
                feature_df=x_mat_weighted)

        return self.plot_silverkite_components(
            components=self.components,
            names=names,
            title=title)

    def get_silverkite_components(
            self,
            df,
            time_col,
            value_col,
            feature_df):
        """Compute the components of a ``Silverkite`` model.

        Notes
        -----
        This function signature is chosen this way so that an user using `forecast_silverkite` can also use
        this function, without any changes to the `forecast_silverkite` function. User can compute `feature_df`
        as follows. Here `model_dict` is the output of `forecast_silverkite`.
        feature_df = model_dict["mod"].coef_ * model_dict["design_mat"]

        The function aggregates components based on the column names of `feature_df`.
        `feature_df` is defined as the patsy design matrix built by `design_mat_from_formula`
        multiplied by the corresponding coefficients, estimated by the silverkite model.

            - ``cst.TREND_REGEX``:  Used to identify `feature_df` columns corresponding to trend.
            See `greykite.common.features.timeseries_features.get_changepoint_features` for details
            about changepoint column names.
            - ``cst.SEASONALITY_REGEX``: Used to identify `feature_df` columns corresponding to seasonality.
            This means to get correct seasonalities, the user needs to provide seas_names.
            See `greykite.common.features.timeseries_features.get_fourier_col_name` for details
            about seasonality column names.
            - ``cst.EVENT_REGEX``: Used to identify `feature_df` columns corresponding to events such as holidays.
            See `~greykite.common.features.timeseries_features.add_daily_events` for details
            about event column names.

        Parameters
        ----------
        df : `pandas.DataFrame`
            A dataframe containing `time_col`, `value_col` and `regressors`.
        time_col : `str`
            The name of the time column in ``df``.
        value_col : `str`
            The name of the value column in ``df``.
        feature_df : `pandas.DataFrame`
            A dataframe containing feature columns and values.

        Returns
        -------
        components : `pandas.DataFrame`
            Contains the components of the model. Same number of rows as `df`. Possible columns are

            - `"time_col"`: same as input ``time_col``.
            - `"value_col"`: same as input ``value_col``.
            - `"trend"`: column containing the trend.
            - `"autoregression"`: column containing the autoregression.
            - `"lagged_regressor"`: column containing the lagged regressors.
            - `"DAILY_SEASONALITY"`: column containing daily seasonality.
            - `"WEEKLY_SEASONALITY"`: column containing weekly seasonality.
            - `"MONTHLY_SEASONALITY"`: column containing monthly seasonality.
            - `"QUARTERLY_SEASONALITY"`: column containing quarterly seasonality.
            - `"YEARLY_SEASONALITY"`: column containing yearly seasonality.
            - `"events"`: column containing events e.g. holidays effect.
            - `"residual"`: column containing residuals.

        """
        if feature_df is None or feature_df.empty:
            raise ValueError("feature_df must be non-empty")

        if df.shape[0] != feature_df.shape[0]:
            raise ValueError("df and feature_df must have same number of rows.")

        feature_cols = feature_df.columns
        components = df[[time_col, value_col]]

        # gets trend (this includes interaction terms)
        trend_cols = get_pattern_cols(feature_cols, cst.TREND_REGEX, f"{cst.SEASONALITY_REGEX}|{cst.LAG_REGEX}")
        if trend_cols:
            components["trend"] = feature_df[trend_cols].sum(axis=1)

        # gets lagged terms (auto regression, lagged regressors and corresponding interaction terms)
        lag_cols = get_pattern_cols(feature_cols, cst.LAG_REGEX)
        if lag_cols:
            ar_cols = [lag_col for lag_col in lag_cols if value_col in lag_col]
            if ar_cols:
                components["autoregression"] = feature_df[ar_cols].sum(axis=1)
            lagged_regressor_cols = [lag_col for lag_col in lag_cols if value_col not in lag_col]
            if lagged_regressor_cols:
                components["lagged_regressor"] = feature_df[lagged_regressor_cols].sum(axis=1)

        # gets seasonalities
        seas_cols = get_pattern_cols(feature_cols, cst.SEASONALITY_REGEX)
        seas_components_dict = self._silverkite_components_enum.__dict__["_member_names_"].copy()
        for seas in seas_components_dict:
            seas_pattern = self._silverkite_components_enum[seas].value.ylabel
            seas_pattern_cols = get_pattern_cols(seas_cols, seas_pattern)
            if seas_pattern_cols:
                components[seas] = feature_df[seas_pattern_cols].sum(axis=1)

        # gets events (holidays for now)
        event_cols = get_pattern_cols(feature_cols, cst.EVENT_REGEX)
        if event_cols:
            components["events"] = feature_df[event_cols].sum(axis=1)

        # calculates residuals
        components["residual"] = df[value_col].values - feature_df.sum(axis=1).values

        # gets trend changepoints
        # keeps this column as the last column of the df
        if trend_cols:
            changepoint_dates = get_trend_changepoint_dates_from_cols(trend_cols=trend_cols)
            if changepoint_dates:
                ts = pd.to_datetime(components[time_col])
                changepoints = [1 if t in changepoint_dates else 0 for t in ts]
                components["trend_changepoints"] = changepoints

        return components

    def group_silverkite_seas_components(self, df):
        """Groups and renames``Silverkite`` seasonalities.

        Parameters
        ----------
        df: `pandas.DataFrame`
            DataFrame containing two columns:

            - ``time_col``: Timestamps of the original timeseries.
            - ``seas``: A seasonality component. It must match a component name from the
            `~greykite.algo.forecast.silverkite.constants.silverkite_component.SilverkiteComponentsEnum`.

        Returns
        -------
            `pandas.DataFrame`
            DataFrame grouped by the time feature corresponding to the seasonality
            and renamed as defined in
            `~greykite.algo.forecast.silverkite.constants.silverkite_component.SilverkiteComponentsEnum`.
        """
        time_col, seas = df.columns
        groupby_time_feature = self._silverkite_components_enum[seas].value.groupby_time_feature
        xlabel = self._silverkite_components_enum[seas].value.xlabel
        ylabel = self._silverkite_components_enum[seas].value.ylabel

        def grouping_func(grp):
            return np.nanmean(grp[seas])

        result = add_groupby_column(
            df=df,
            time_col=time_col,
            groupby_time_feature=groupby_time_feature)
        grouped_df = grouping_evaluation(
            df=result["df"],
            groupby_col=result["groupby_col"],
            grouping_func=grouping_func,
            grouping_func_name=ylabel)
        grouped_df.rename({result["groupby_col"]: xlabel}, axis=1, inplace=True)
        return grouped_df

    def plot_silverkite_components(
            self,
            components,
            names=None,
            title=None):
        """Plot the components of a ``Silverkite`` model.

        Parameters
        ----------
        components : `pandas.DataFrame`
            A dataframe containing the components of a silverkite model, similar to the output
            of `~greykite.sklearn.estimator.silverkite_diagnostics.get_silverkite_components`.
        names: `list` [`str`], optional, default `None`
                Names of the components to be plotted e.g. names = ["trend", "DAILY_SEASONALITY"].
                See `~greykite.sklearn.estimator.silverkite_diagnostics.get_silverkite_components`
                for the full list of valid names.
                If `None`, all the available components are plotted.
        title: `str`, optional, default `None`
                Title of the plot. If `None`, default title is "Component plot".

        Returns
        -------
        fig: `plotly.graph_objects.Figure`
            Figure plotting components against appropriate time scale.

        Notes
        -----
        If names in `None`, all the available components are plotted.
        ``value_col`` is always plotted in the first panel, as long as there is a match between
        given ``names`` list and ``components.columns``.

        See Also
        --------
        `~greykite.sklearn.estimator.silverkite_diagnostics.get_silverkite_components`
        """

        time_col, value_col = components.columns[:2]
        if "trend_changepoints" in components.columns:
            trend_changepoints = components[time_col].loc[components["trend_changepoints"] == 1].tolist()
            components = components.drop("trend_changepoints", axis=1)
        else:
            trend_changepoints = None
        if names is None:
            names_kept = list(components.columns)[1:]  # do not include time_col
        else:
            # loops over components.columns to maintain the order of the components
            names_kept = [component for component in list(components.columns) if component in names]
            names_removed = set(names) - set(components.columns)

            if not names_kept:
                raise ValueError("None of the provided components have been specified in the model.")
            elif names_removed:
                warnings.warn(f"The following components have not been specified in the model: "
                              f"{names_removed}, plotting the rest.")
            if names_kept[0] != value_col:
                names_kept.insert(0, value_col)

        num_rows = len(names_kept)
        fig = make_subplots(rows=num_rows, cols=1, vertical_spacing=0.35 / num_rows)
        if title is None:
            title = "Component plots"
        fig.update_layout(dict(showlegend=True, title=title, title_x=0.5, height=350 * num_rows))

        for ind, name in enumerate(names_kept):
            df = components[[time_col, name]]
            if "SEASONALITY" in name:
                df = self.group_silverkite_seas_components(df)

            xlabel, ylabel = df.columns
            row = ind + 1
            fig.append_trace(go.Scatter(
                x=df[xlabel],
                y=df[ylabel],
                name=name,
                mode="lines",
                opacity=0.8,
                showlegend=False
            ), row=row, col=1)

            # `showline = True` shows a line only along the axes. i.e. for xaxis it will line the bottom
            # of the image, but not top. Adding `mirror = True` also adds the line to the top.
            fig.update_xaxes(title_text=xlabel, showline=True, mirror=True, row=row, col=1)
            fig.update_yaxes(title_text=ylabel, showline=True, mirror=True, row=row, col=1)

        # plot trend change points
        if trend_changepoints is not None and "trend" in names_kept:
            for i, cp in enumerate(trend_changepoints):
                show_legend = (i == 0)
                fig.append_trace(
                    go.Scatter(
                        name="trend change point",
                        mode="lines",
                        x=[cp, cp],
                        y=[components["trend"].min(), components["trend"].max()],
                        line=go.scatter.Line(
                            color="#F44336",  # red 500
                            width=1.5,
                            dash="dash"),
                        showlegend=show_legend),
                    row=names_kept.index("trend") + 1,
                    col=1)

        return fig
