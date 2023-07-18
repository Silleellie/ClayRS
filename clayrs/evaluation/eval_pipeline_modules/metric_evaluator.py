from __future__ import annotations
from typing import List, Tuple, Union, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from clayrs.content_analyzer.ratings_manager.ratings import Prediction, Rank, Ratings
    from clayrs.evaluation.metrics.metrics import Metric

from clayrs.utils.context_managers import get_progbar


class MetricEvaluator:
    """
    Module of the Evaluation pipeline which, has the task to evaluate recommendations generated for every user with a
    list of metric specified

    This module can also be used to evaluate recommendations generated from outside. In this case, the usage is the
    following\n
    MANUAL USAGE::

        # Let's say we have outside recommendations for 2 splits, and
        # we want to evaluate them both

        # First we must wrap our generated recommendations into 'Split' objects
        split1 = Split(pred1, truth1)
        split2 = Split(pred2, truth2)

        # Then we instantiate the MetricCalculator passing the split list
        mc = MetricCalculator([split1, split2])

        # Then simply call the 'eval_metrics' method with the list of metrics you'd like to evaluate
        mc.eval_metrics([Precision(), Recall()])

    Args:
        predictions_truths (List[Split]): List of splits that need to be evaluated. Pass your custom splits here if you
            want to evaluate recommendations generated from the outside.
            This is set to None by default, meaning that splits that will be evaluated are those generated by
            the PredictionCalculator module of the EvalModel pipeline

    """

    # [ (total_pred, total_truth), (total_pred, total_truth) ...]
    def __init__(self, pred_list: Union[List[Prediction], List[Rank]], truth_list: List[Ratings]):

        self._pred_list = pred_list
        self._truth_list = truth_list

    def __repr__(self):
        return f'MetricEvaluator(pred_list={self._pred_list}, truth_list={self._truth_list})'

    def eval_metrics(self, metric_list: List[Metric]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Method which effectively evaluates recommendations generated with the list of metric passed as argument.

        It returns two Pandas DataFrame, the first one containing system results on all metrics specified, the second
        one containing each users results for every metric eligible

        Args:
            metric_list (List[Metric]): List of metric on which recommendations need to be evaluated

        Returns:
            The first DataFrame will contain the system result for every metric specified inside the metric list,

            The second DataFrame will contain every user results for every metric eligible
        """

        frames_to_concat_users = []
        frames_to_concat_system = []

        with get_progbar(metric_list) as pbar:

            for metric in pbar:
                pbar.set_description(desc=f"Performing {metric}")

                metric_result_list = []

                for pred, truth in zip(self._pred_list, self._truth_list):
                    if len(pred) != 0 and len(truth) != 0:

                        # users can be different between predictions and truth, we only consider those
                        # who are in both
                        common_user_ids = list(
                            set(pred.unique_user_id_column).intersection(set(truth.unique_user_id_column))
                        )

                        prediction_user_idxs = pred.user_map.convert_seq_str2int(common_user_ids)
                        truth_user_idxs = truth.user_map.convert_seq_str2int(common_user_ids)

                        pred = pred.filter_ratings(prediction_user_idxs)
                        truth = truth.filter_ratings(truth_user_idxs)

                        metric_result = metric.perform(Split(pred, truth))

                        metric_result_list.append(metric_result)

                # if in future results for each fold for each user
                # set index as from_id and concat axis = 1
                total_results_metric = pd.concat(metric_result_list)

                if not total_results_metric.empty:
                    total_results_metric = total_results_metric.set_index('user_id')
                    system_results = total_results_metric.loc[['sys']]

                    # this means that if a system result is nan, it won't be present in the final df.
                    # Maybe there's a better solution?
                    # (This removal is done in case metric for users and system have different name eg. AP for users and
                    # MAP for sys)
                    system_results = system_results.dropna(axis='columns', how='all')

                    each_user_result = total_results_metric.drop(['sys'])
                    each_user_result = each_user_result.dropna(axis=1, how='all')

                    if not each_user_result.empty:
                        frames_to_concat_users.append(each_user_result)

                    if not system_results.empty:
                        frames_to_concat_system.append(system_results)

        # concat horizontally results of each metric both for users and system
        final_result_users = pd.DataFrame(columns=['user_id'])
        if len(frames_to_concat_users) != 0:
            final_result_users = pd.concat(frames_to_concat_users, axis=1)

            # for users calculate the mean
            final_result_users = final_result_users.groupby('user_id').mean()

        final_result_system = pd.DataFrame(columns=['user_id'])
        if len(frames_to_concat_system) != 0:
            final_result_system = pd.concat(frames_to_concat_system, axis=1)

            # replace index of system results in order to better identify results of each fold
            new_index = [f'sys - fold{i + 1}' for i in range(len(final_result_system))]
            final_result_system['user_id'] = new_index
            final_result_system = final_result_system.set_index('user_id')

            # add mean results as a row
            system_means = list(final_result_system.mean().values)
            final_result_system.loc['sys - mean'] = system_means

        return final_result_system, final_result_users


class Split:
    """
    Class container for two pandas DataFrame

    It may represent a split containing 'train set' and 'test set', or a split containing a ground truth and predictions
    for it, etc.

    Once instantiated, one can access the two dataframes in different ways:

    | > sp = Split()
    | > # Various ways of accessing the FIRST DataFrame
    | > sp.train
    | > sp.pred
    | > sp.first
    | >
    | > # Various ways of accessing the SECOND DataFrame
    | > sp.test
    | > sp.truth
    | > sp.second

    Args:
        first_set (pd.DatFrame): the first DataFrame to contain. If not specified, an empty DataFrame with 'from_id',
            'to_id', and 'score' column will be instantiated
        second_set (pd.DataFrame): the second DataFrame to contain. If not specified, an empty DataFrame with 'from_id',
            'to_id' and 'score' column will be instantiated
    """

    def __init__(self,
                 first_set: Ratings,
                 second_set: Ratings):

        self.__dict__['first'] = first_set
        self.__dict__['second'] = second_set

        self.__dict__['_valid_first_name'] = ['train', 'pred', 'first']
        self.__dict__['_valid_second_name'] = ['test', 'truth', 'second']

    def __getattr__(self, name):
        if name in self._valid_first_name:
            return self.first
        elif name in self._valid_second_name:
            return self.second

    def __setattr__(self, name, value):
        if name in self._valid_first_name:
            super().__setattr__('first', value)
        elif name in self._valid_second_name:
            super().__setattr__('second', value)
