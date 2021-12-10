from typing import List, Tuple

from orange_cb_recsys.recsys.partitioning import Split
from orange_cb_recsys.evaluation.metrics.metrics import Metric
from orange_cb_recsys.utils.const import progbar, eval_logger

import pandas as pd


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
    def __init__(self, predictions_truths: List[Split] = None):
        self._split_list = predictions_truths

    def eval_metrics(self, metric_list: List[Metric]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Method which effectively evaluates recommendations generated with the list of metric passed as argument.

        It returns two Pandas DataFrame, the first one containing system results on all metrics specified, the second
        one containing each users results for every metric eligible

        Args:
            metric_list (List[Metric]): List of metric on which recommendations need to be evaluated

        Returns:
            Two pandas DataFrame, the first will contain the system result for every metric specified inside the metric
            list, the second one will contain every user results for every metric eligible
        """

        frames_to_concat = []

        eval_logger.info('Performing metrics chosen')

        for metric in progbar(metric_list, prefix='Performing {}:', substitute_with_current=True):

            metric_result_list = []

            if self._split_list is None:
                split_list = metric._get_pred_truth_list()
            else:
                split_list = self._split_list

            for split in split_list:
                if not split.pred.empty and not split.truth.empty:
                    from_id_valid = split.pred['from_id']
                    # Remove from truth item of which we do not have predictions
                    split.truth = split.truth.query('from_id in @from_id_valid')
                    metric_result = metric.perform(split)
                    metric_result_list.append(metric_result)

            total_results_metric = pd.concat(metric_result_list)

            if not total_results_metric.empty:
                total_results_metric = total_results_metric.groupby('from_id').mean()

                total_results_metric.index.name = 'from_id'

                frames_to_concat.append(total_results_metric)

        final_result = pd.concat(frames_to_concat, axis=1)

        system_results = final_result.loc[['sys']]
        each_user_result = final_result.drop(['sys'])

        each_user_result = each_user_result.dropna(axis=1, how='all')

        return system_results, each_user_result
